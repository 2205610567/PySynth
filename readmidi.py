#!/usr/bin/env python

# Read MIDI file track and synthesize with PySynth A

# Based on code from https://github.com/osakared/midifile.py

# Original license:

"""
Copyright (c) 2014, Thomas J. Webb
All rights reserved.

Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions are met:

* Redistributions of source code must retain the above copyright notice, this
  list of conditions and the following disclaimer.

* Redistributions in binary form must reproduce the above copyright notice,
  this list of conditions and the following disclaimer in the documentation
  and/or other materials provided with the distribution.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE
FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
"""

import struct

class Note(object):
	"Represents a single midi note"
	
	note_names = ['A', 'A#', 'B', 'C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#']
	
	def __init__(self, channel, pitch, velocity, start, duration = 0):
		self.channel = channel
		self.pitch = pitch
		self.velocity = velocity
		self.start = start
		self.duration = duration
	
	def __str__(self):
		s = Note.note_names[(self.pitch - 9) % 12]
		s += str(self.pitch // 12 - 1)
		s += " " + str(self.velocity)
		s += " " + str(self.start) + " " + str(self.start + self.duration) + " "
		return s
	
	def get_end(self):
		return self.start + self.duration

def notes_from_xml(element):
	track = []
	for child in element.childNodes:
		if child.attributes and (child.tagName == 'MidiNote' or child.tagName == 'TempMidiNote'):
			try:
				track.append(Note(0, int(child.getAttribute('pitch')), int(child.getAttribute('velocity')), float(child.getAttribute('start')), float(child.getAttribute('duration'))))
			except Exception as e:
				print("Cannot parse MidiNote or TempMidiNote: " + str(e))
	return track

def notes_to_str(notes):
	s = ""
	for note in notes:
		s += str(note) + " "
	return s

class MidiFile(object):
	"Represents the Notes in a midi file"
	
	def read_byte(self, file):
		return struct.unpack('B', file.read(1))[0]
	
	def read_variable_length(self, file, counter):
		counter -= 1
		num = self.read_byte(file)
		
		if num & 0x80:
			num = num & 0x7F
			while True:
				counter -= 1
				c = self.read_byte(file)
				num = (num << 7) + (c & 0x7F)
				if not (c & 0x80):
					break
		
		return (num, counter)

	def find_track(self, file, pos = 0):
		"Find position of next track in file"
		file.seek(pos)
		b = file.read(10000)
		p = b.find(b"MTrk")
		file.seek(p + pos)
	
	def __init__(self, file_name):
		self.tempo = 120
		try:
			file = open(file_name, 'rb')
			if file.read(4) != b'MThd': raise Exception('Not a midi file')
			self.file_name = file_name
			size = struct.unpack('>i', file.read(4))[0]
			if size != 6: raise Exception('Unusual midi file with non-6 sized header')
			self.format = struct.unpack('>h', file.read(2))[0]
			self.track_count = struct.unpack('>h', file.read(2))[0]
			self.time_division = struct.unpack('>h', file.read(2))[0]

			# Now to fill out the arrays with the notes
			self.tracks = []
			for i in range(0, self.track_count):
				self.tracks.append([])

			for nn, track in enumerate(self.tracks):
				abs_time = 0.
				self.find_track(file, file.tell())
				if file.read(4) != b'MTrk': raise Exception('Not a valid track')
				size = struct.unpack('>i', file.read(4))[0]

				# To keep track of running status
				last_flag = None
				while size > 0:
					delta, size = self.read_variable_length(file, size)
					delta /= float(self.time_division)
					abs_time += delta

					size -= 1
					flag = self.read_byte(file)
					# Sysex, which we aren't interested in
					if flag == 0xF0 or flag == 0xF7:
						# print "Sysex"
						while True:
							size -= 1
							if self.read_byte(file) == 0xF7: break
					# Meta, which we also aren't interested in
					elif flag == 0xFF:
						size -= 1
						type = self.read_byte(file)
						if type == 0x2F:
							break
						print("Meta: " + str(type))
						length, size = self.read_variable_length(file, size)
						message = file.read(length)
						# if type not in [0x0, 0x7, 0x20, 0x2F, 0x51, 0x54, 0x58, 0x59, 0x7F]:
						print(length, message)
						if type == 0x51:	# qpm/bpm
							# http://www.recordingblogs.com/sa/Wiki?topic=MIDI+Set+Tempo+meta+message
							self.tempo = 6e7 / struct.unpack('>i', b'\x00' + message)[0]
							print("tempo =", self.tempo, "bpm")
					# Midi messages
					else:
						if flag & 0x80:
							type_and_channel = flag#self.read_byte(file)
							size -= 1
							param1 = self.read_byte(file)
							last_flag = flag
						else:
							type_and_channel = last_flag
							param1 = flag
						type = ((type_and_channel & 0xF0) >> 4)
						channel = type_and_channel & 0xF
						size -= 1
						param2 = self.read_byte(file)
						
						# For now, anyway, we only care about midi ons and midi offs
						if type == 0x9:
							track.append(Note(channel, param1, param2, abs_time))
						elif type == 0x8:
							for note in reversed(track):
								if note.channel == channel and note.pitch == param1:
									note.duration = abs_time - note.start
									break

		except Exception as e:
			print("Cannot parse midi file: " + str(e))
			#raise
		finally:
			file.close()
	
	def __str__(self):
		s = ""
		for i, track in enumerate(self.tracks):
			s += "Track " + str(i+1) + "\n"
			for note in track:
				s += str(note) + "\n"
		return s

def getdur(a, b):
	"Calculate note length for PySynth"
	return 4 / (b - a)

if __name__ == "__main__":
	import sys
	m = MidiFile(sys.argv[1])
	for t, n in enumerate(m.tracks):
		if len(n) > 0:
			print(t, n[0], len(n))
	song = []
	last1, last2 = -1, -1
	for n in m.tracks[1]:
		nn = str(n).split()
		start, stop = float(nn[2]), float(nn[3])
		# PySynth is monophonic:
		if start == last1:
			continue
		# Add rests:
		if last2 > -1 and start - last2 > 0:
			song.append(('r', getdur(last2, start)))

		last1 = start
		last2 = stop
		song.append((nn[0].lower(), getdur(start, stop)))
	print(song)
	import pysynth
	pysynth.make_wav(song, fn = "midi.wav", bpm = m.tempo)

