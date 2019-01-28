#!/bin/env python
# -*- coding: utf-8 -*-

# Multithreaded application for downloading tracks from user's Spotify favorites playlist
# Michael Simpson
# 01/27/19 -- github.com/misimpso/

from __future__ import division
from curses import wrapper, ERR
from mutagen.mp3 import MP3, EasyMP3
from mutagen.id3 import APIC, WXXX
from mutagen.id3 import ID3 as OldID3
from os import mkdir
from os.path import isfile, isdir, dirname, exists, join
from Queue import Queue, Empty
from unidecode import unidecode

import re
import os
import requests
import shutil
import soundcloud
import threading

# Worker class being handled by thread
class DownloadWorker(threading.Thread):

	def __init__(self, id, tasks, client_id, output_directory, result_q):
		
		# Make sure child is behaving (cooperative multiple inheritance )
		# https://www.python-course.eu/python3_multiple_inheritance.php
		super(DownloadWorker, self).__init__()
		
		# Thread attributes
		self.id = id
		self.tasks = tasks
		self.client_id = client_id
		self.output_directory = output_directory
		self.result_q = result_q
		
		# Event for thread stopping
		self.stop_request = threading.Event()
	
	# Main loop of thread - deque next task and download it
	def run(self):
		while not self.stop_request.isSet():
			try:
				curr_task = self.tasks.get(True, 0.05)
				self.download(curr_task)
				# self.tag_file(curr_task)
				self.tasks.task_done()
			except Empty:
				self.result_q.put((self.id, 0, "Done"))
				continue
		
	# Assemble request and stream music data from spotify servers
	def download(self, curr_task):
		# Download chunk size
		chunk_size = 8192
		
		# Assemble response with thread parameters
		response = requests.get("{}?client_id={}".format(curr_task.fields()['stream_url'], self.client_id), stream=True)
		
		# Get total size of file
		total_size = int(response.headers['content-length'].strip())
		
		# Create new .mp3 file and write to it with data received from response
		with open(join(self.output_directory, convert_unicode(curr_task.fields()["user"]["username"]), "{}.mp3".format(convert_unicode(curr_task.fields()["title"]))), 'ab+') as mp3:
			
			# Keep track of downloaded bytes for progress bar
			bytes_so_far = 0
			
			# Loop over info in response and write to file in chunk-sized increments 
			for chunk in response.iter_content(chunk_size):
				mp3.write(chunk)
				bytes_so_far += len(chunk)
				percent = round((float(bytes_so_far) / total_size), 4)
				
				# Enqueue status so far
				self.result_q.put((self.id, percent, "Downloading /// {} -- {}".format(convert_unicode(curr_task.fields()["user"]["username"]), convert_unicode(curr_task.fields()["title"]))))
			
			# Enqueue status when finished downloading
			self.result_q.put((self.id, percent, "Completed ///// {} -- {}".format(convert_unicode(curr_task.fields()["user"]["username"]), convert_unicode(curr_task.fields()["title"]))))
		
		# Clean up after ourselves
		response = None
		
	# Tag file with meta data -- not fully implemented yet
	def tag_file(self, curr_task):
		audio = EasyMP3(join(self.output_directory, convert_unicode(curr_task.fields()["user"]["username"]), "{}.mp3".format(convert_unicode(curr_task.fields()["title"]))))
		audio["artist"] = curr_task.fields()["user"]["username"]
		audio["title"] = curr_task.fields()["title"]
		audio["album"] = "Soundcloud"
		audio["tracknumber"] = curr_task.fields()["track_num"]
		audio.save()
		
		# artwork_url = curr_task.fields()["artwork_url"]
		
		# if artwork_url:
			# artwork_url = artwork_url.replace('https', 'http')
			# mime = 'image/jpeg'
			# if '.jpg' in artwork_url:
				# mime = 'image/jpeg'
			# if '.png' in artwork_url:
				# mime = 'image/png'

			# if '-large' in artwork_url:
				# new_artwork_url = artwork_url.replace('-large', '-t500x500')
				# try:
					# image_data = requests.get(new_artwork_url).content
				# except Exception as e:
					# # No very large image available.
					# image_data = requests.get(artwork_url).content
			# else:
				# image_data = requests.get(artwork_url).content

			# audio = MP3(filename, ID3=OldID3)
			# audio.tags.add(
				# APIC(
					# encoding=3,  # 3 is for utf-8
					# mime=mime,
					# type=3,  # 3 is for the cover image
					# desc='Cover',
					# data=image_data
				# )
			# )
			# audio.save()
	
	# Thread helper method for stopping thread and ensuring parent stops thread
	def join(self):
		# self.result_q.put((self.id, 1.1, "Joining"))
		self.stop_request.set()
		super(DownloadWorker, self).join()
		
# Completely remove any special characters
def convert_unicode(s):
	s = unidecode(s)
	s = re.sub(r'[/\\:*?"<>|]', '-', s)
	s = s.replace('.', '')
	s = s.strip()
	return s

# Parent class for connecting to spotify, allocating directories, and spawning download workers
class DownloadManager:
	def __init__(self):
	
		# 8 char string User ID 
		self.user_id = 'XXXXXXXX' # 8 char string
		
		# Soundcloud API client ID
		self.client_id = 'XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX' # 32 char string
		
		# Output directory
		self.output_directory = join(os.path.dirname(os.path.realpath(__file__)), 'Music')
		
		# Connect to soundcloud API
		print("Connecting to Soundcloud API...")
		self.client = soundcloud.Client(client_id=self.client_id)
		print("Connected!")
		
		# Get list of liked tracks from user
		self.tracks = self.client.get('users/{}/favorites'.format(self.user_id), linked_partitioning=1)
		
		# Make output dir if needed
		if not isdir(self.output_directory):
			mkdir(self.output_directory)
			
		# Check for new tracks and handle multithreading
		self.check_new_tracks()
		
		# Init GUI layer and give input function for viewing
		# Input funtion is multithreaded spawning of download workers
		wrapper(self.spawn_workers)
		
		print("Done!")
		
	def check_new_tracks(self):
	
		# List for new tracks to DL
		self.new_tracks = []
		
		# Track numbering base line
		self.track_num = 1
		print("Getting new tracks...")
		
		# Check for reference to more tracks available
		while "next_href" in self.tracks.keys():
		
			# Loop through current tracks in collection
			for track in self.tracks.collection:
			
				# Add track number to track object
				track.fields()["track_num"] = self.track_num
				
				# Check if current track's artist has a folder in destination
				# If it doesn't, then track is new, make directory and add track to new_tracks
				if not isdir(join(self.output_directory, convert_unicode(track.fields()["user"]["username"]))):
					mkdir(join(self.output_directory, convert_unicode(track.fields()["user"]["username"])))
					self.new_tracks.append(track)
					
				# Else artist's directory exists, but check if track name is there and add if new
				elif not isfile(join(self.output_directory, convert_unicode(track.fields()["user"]["username"]), "{}.mp3".format(convert_unicode(track.fields()["title"])))):
					self.new_tracks.append(track)
				
				self.track_num += 1
				
			# Set current track obj to next if there
			self.tracks = self.client.get(self.tracks.next_href)
			
	def spawn_workers(self, scr):
	
		# if no new tracks, then we're done
		if len(self.new_tracks) == 0:
			print("Nothing new!")
			return
			
		# else we got some work to do
		else:
		
			# Clear the screen
			scr.clear()
			
			# Number of workers to be spawned
			num_workers = 5 # int(len(self.new_tracks) / 10)
			
			# Queues for work to do and results from workers
			self.task_q = Queue()
			self.result_q_list = [Queue() for i in range(0, num_workers)]
			
			# Create and keep track of workers
			# - Record
			manifest = {i : {"prog" : 0, "task" : ''} for i in range(0, num_workers)}
			# - Workers
			pool = [DownloadWorker(i, self.task_q, self.client_id, self.output_directory, self.result_q_list[i]) for i in range(0, num_workers)]
			
			# Rev up those fryers
			for thread in pool:
				thread.start()
			
			# Add work to the queue
			for t in self.new_tracks:
				self.task_q.put(t)
			
			# Num completed tracks
			completed_tracks = 0
			
			# While tracks still downloading, check queue
			while completed_tracks < len(self.new_tracks):
				
				# Get list of latests statuses from each worker's results queue
				results = []
				for i in range(0, num_workers):
					try:
						results.append(self.result_q_list[i].get(True, 0.05))
					except Empty:
						continue
				
				for r in results:
				
					# if % is greater than 1, and status is Completed
					if r[1] >= 1.0 and r[2].startswith("Completed"):
						completed_tracks += 1
					
					# Update task progress
					manifest[r[0]]["prog"] = r[1]
					
					# Update task status
					manifest[r[0]]["task"] = r[2]
				
				# ~~~ PRINTING ~~~
				
				# Add header string
				scr.addstr(0, 0, "Downloaded {} / {}".format(completed_tracks, len(self.new_tracks)))
				
				# Print out manifest
				for m in sorted(manifest.keys()):
					try:
						scr.addstr(int(4 * m) + 1, 0, "Thread - {} :".format(m))
						scr.addstr(int(4 * m) + 2, 0, "{: <80}".format(manifest[m]["task"][:80]))
						scr.addstr(int(4 * m) + 3, 0, "[{: <10}] {: >6.2f}%".format(int(manifest[m]["prog"] * 10) * "#", manifest[m]["prog"] * 100))
						scr.addstr(int(4 * m) + 4, 0, "")
					except ERR as e:
						curses.curses.endwin()
						print(e)
					
				scr.refresh()
				
				# ~~~~~~~~~~~~~~~~
			
			# scr.addstr(0, 0, "Joining?")
			
			# Clean up threads
			for thread in pool:
				thread.join()

if __name__ == '__main__':

	dm = DownloadManager()