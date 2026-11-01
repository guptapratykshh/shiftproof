"""Deterministic non-silent PCM for transport tests, never human speech evidence."""
import math
import struct

def pcm_frames(count, rate=16000):
    return b''.join(struct.pack('<h', int(4000 * math.sin(2 * math.pi * 440 * i / rate))) for i in range(count))
