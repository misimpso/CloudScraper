#!/bin/env python3

# Multithreaded application for downloading tracks from user's Spotify favorites playlist
# Michael Simpson
# 02/17/20 -- github.com/misimpso/

from contextlib import closing
from mp3_tagger import MP3File, VERSION_BOTH
from unidecode import unidecode

import asyncio
import aiohttp
import emoji
import os
import re
import soundcloud
import sys
import tqdm


# Completely remove any special characters
def convert_unicode(s):
	s = re.sub(r'[\&]+', u'and', s)
	s = re.sub(r'[\\\/\\.\?\*\+\"\'\|\:\?\<\>]+', u' ', s)
	s = emoji.get_emoji_regexp().sub(u'', s)
	s = unidecode(s)
	s = s.strip()
	return s


def get_all_tracks():
	client = soundcloud.Client(client_id=client_id)
	print("Connected! Getting tracks ...")
	tracks_url = f'users/{user_id}/favorites'
	new_tracks = []
	track_num = 1
	tracks = client.get(tracks_url, linked_partitioning=1)
	while "next_href" in tracks.keys():
		for track in tracks.collection:
			track.obj['track_num'] = track_num
			track.obj['user']['username'] = convert_unicode(track.obj['user']['username'])
			track.obj['title'] = convert_unicode(track.obj['title'])
			artist_dir = os.path.join(output_directory, track.obj['user']['username'])
			track_dir = os.path.join(artist_dir, f"{track.obj['title']}.mp3")
			if os.path.isfile(track_dir) and not get_all_bool:
				continue
			elif not os.path.isdir(artist_dir):
				os.mkdir(artist_dir)
			new_tracks.append(track.obj)
			track_num += 1
		tracks = client.get(tracks.next_href)
	return new_tracks


async def download_track(session, track, progress_queue):
	output_file = os.path.join(
		output_directory,
		track['user']['username'],
		f"{track['title']}.mp3",
	)
	chunk_size = 2**10
	async with session.get(track['stream_url'], params={'client_id': client_id}) as response:
		target = f"{track['user']['username']} - {track['title']}"
		size = int(response.headers.get('content-length', 0)) or None
		position = await progress_queue.get()
		progress_bar = tqdm.tqdm(
			desc=target,
			total=size,
			position=position,
			leave=False,
			unit='iB',
			ascii=True,
			unit_scale=True,
		)
		with open(output_file, 'wb+') as f:
			async for chunk in response.content.iter_chunked(chunk_size):
				f.write(chunk)
				progress_bar.update(len(chunk))

	mp3 = MP3File(output_file)
	mp3.set_version(VERSION_BOTH)
	mp3.song = track['title']
	mp3.artist = track['user']['username']
	mp3.track = f"{track['track_num']}"
	mp3.album = 'Soundcloud'
	mp3.save()

	await progress_queue.put(position)


async def main(loop):
	new_tracks = get_all_tracks()
	if len(new_tracks) == 0:
		print("No new tracks.")
		return
	progress_queue = asyncio.Queue(loop=loop)
	for pos in range(min(15, len(new_tracks))):
		progress_queue.put_nowait(pos)
	async with aiohttp.ClientSession(loop=loop) as session:
		return await asyncio.gather(*[download_track(session, track, progress_queue) for track in new_tracks])


if __name__ == '__main__':

	user_id = 'XXXXXXXX' # 8 char string '16273146'
	client_id = 'XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX' # 32 char string
	output_directory = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'Music2')

	if not os.path.isdir(output_directory):
		os.mkdir(output_directory)

	get_all_bool = sys.argv[1].lower() == 'a' if len(sys.argv[1:]) else False

	with closing(asyncio.get_event_loop()) as loop:
		loop.run_until_complete(main(loop))