"""Fictional actors for offline engine tests and evaluation, never login identities."""
from .models import Actor

ACTORS = {
    'operator': Actor(id='op-arjun', name='Arjun Mehta', role='operator'),
    'quality': Actor(id='qa-kavya', name='Kavya Rao', role='quality'),
    'supervisor': Actor(id='sup-neha', name='Neha Sharma', role='supervisor'),
}

