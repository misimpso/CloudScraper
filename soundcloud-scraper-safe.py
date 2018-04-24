
# -*- coding: utf-8 -*-

import sys
import json
import re
import os
import requests
import soundcloud
import simplejson

from os import listdir, access, mkdir, W_OK
from os.path import isfile, join, isdir, dirname, exists, join
from types import *

from mutagen.mp3 import MP3, EasyMP3
from mutagen.id3 import APIC, WXXX
from mutagen.id3 import ID3 as OldID3
from unidecode import unidecode

def getFoldersInDirectory(directory):
	# directory folders query 
	files = [ f for f in listdir(directory) if isdir(join(directory, f))]
	return files
	
def getFilesInDirectory(directory):
	# directory files query 
	files = [ f for f in listdir(directory) if isfile(join(directory, f))]
	return files

def download(trackUrl, artist, title, outputDirectory):
	# print("{}, {}".format(artist, getFoldersInDirectory(outputDirectory)))
	# If Artist doesn't have a folder, make it
	if artist.replace(".", '') not in getFoldersInDirectory(outputDirectory):
		mkdir(join(outputDirectory, artist.replace(".", '')))
	# If Artist has a folder, check if song name is already a file name
	elif title + '.mp3' in getFilesInDirectory(join(outputDirectory, artist.replace(".", ''))):
		print("Already downloaded: {} \ {}\n".format(artist, title))
		return
	# If new song, download it
	print("Downloading: {} \ {}...\n".format(artist, title))
	trackFile = requests.get(trackUrl, stream=True)
	chunkRead(trackFile, join(outputDirectory, artist.replace(".", ''), title + ".mp3"), report_hook=chunkReport)

def chunkReport(bytes_so_far, chunk_size, total_size):
	# calculate and Print download percentage
	percent = float(bytes_so_far) / total_size
	percent = round(percent * 100, 2)
	sys.stdout.write("Downloaded %d of %d bytes (%0.2f%%)\r" % (bytes_so_far, total_size, percent))
	if bytes_so_far >= total_size:
		sys.stdout.write('\n\n')
	
	
def chunkRead(response, output, chunk_size=8192, report_hook=None):
	# Info for chunk report, total and remaining checks of streaming 
	total_size = response.headers['content-length'].strip()
	total_size = int(total_size)
	bytes_so_far = 0
	# If output file hasn't been made, make it, and start writing to it
	with open(output, 'ab+') as mp3:
		# Write chunk info and send progress to chunk report as report hook
		for chunk in response.iter_content(chunk_size):
			bytes_so_far += len(chunk)
			mp3.write(chunk)
			if report_hook:
				report_hook(bytes_so_far, chunk_size, total_size)

# Tag file with meta data
def tag_file(filename, artist, title, year=None, genre=None, artwork_url=None):
	try:
		audio = EasyMP3(filename)
		audio.tags = None
		audio["artist"] = artist
		audio["title"] = title
		if year:
			audio["date"] = str(year)
		if genre:
			audio["genre"] = genre
		audio.save()

		if artwork_url:
			artwork_url = artwork_url.replace('https', 'http')
			mime = 'image/jpeg'
			if '.jpg' in artwork_url:
				mime = 'image/jpeg'
			if '.png' in artwork_url:
				mime = 'image/png'

			if '-large' in artwork_url:
				new_artwork_url = artwork_url.replace('-large', '-t500x500')
				try:
					image_data = requests.get(new_artwork_url).content
				except Exception as e:
					# No very large image available.
					image_data = requests.get(artwork_url).content
			else:
				image_data = requests.get(artwork_url).content

			audio = MP3(filename, ID3=OldID3)
			audio.tags.add(
				APIC(
					encoding=3,  # 3 is for utf-8
					mime=mime,
					type=3,  # 3 is for the cover image
					desc='Cover',
					data=image_data
				)
			)
			audio.save()

		return True

	except Exception as e:
		#puts(colored.red("Problem tagging file: ") + colored.white("Is this file a WAV?") + e)
		print(e)
		return False

# Completely remove any special characters
def convert_unicode(s):
	s = unidecode(s)
	s = re.sub(r'[/\\:*?"<>|]', '-', s)
	s = s.replace('&', 'and')
	s = s.replace('"', '')
	s = s.replace("'", '')
	s = s.replace("/", '')
	s = s.replace("\\", '')
	return s
		
		
def main():
	# My user ID
	user_id = ''   # 8 - digit user ID
	# Soundcloud API client ID
	client_id = '' # 32 - digit client ID
	# Output directory
	outputDirectory = join(os.path.dirname(os.path.realpath(__file__)), 'Music')
	# Connect to soundcloud API
	client = soundcloud.Client(client_id=client_id)
	# Get list of liked tracks from user
	tracks = client.get('users/' + user_id + '/favorites', linked_partitioning=1)
	# Loop over the list of tracks, using pagination to generate updated queries
	while('next_href' in tracks.keys()):
		# Loop over list of favorited tracks
		for track in tracks.collection:
			# Download current track, or skip if already downloaded
			download(track.fields()['stream_url'] + '?client_id=' + client_id, convert_unicode(track.fields()['user']['username']), convert_unicode(track.fields()['title']), outputDirectory):
			# Tag file with meta data
			tag_file(join(outputDirectory, convert_unicode(track.fields()['user']['username']), convert_unicode(track.fields()['title']) + '.mp3'), 
				convert_unicode(track.fields()['user']['username']),
				convert_unicode(track.fields()['title']),
				track.fields()['release_year'],
				track.fields()['genre'],
				track.fields()['artwork_url'],
				)
		# Iterate to next page
		tracks = client.get(tracks.next_href)

if __name__ == '__main__':
	main()