import os
import django
from django.db.models import Q

# Set up Django environment
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "acs.settings")
django.setup()

from visitors.models import Event, Session, Camera

def initialize_sessions():
    # Get all events ordered by license_plate and timestamp
    events = Event.objects.select_related('camera').order_by('license_plate', 'timestamp')

    current_plate = None
    in_event = None
    sessions_created = 0

    for event in events:
        if event.license_plate != current_plate:
            # New license plate, reset in_event
            current_plate = event.license_plate
            in_event = None

        if event.camera.is_entrance:
            # This is an entrance event
            in_event = event
        elif in_event and not event.camera.is_entrance:
            # This is an exit event and we have a corresponding entrance event
            if in_event.access_granted or event.access_granted:
                Session.objects.create(
                    in_event=in_event,
                    out_event=event,
                    in_event_type='auto',
                    out_event_type='auto'
                )
                sessions_created += 1
            in_event = None  # Reset in_event after processing

    print(f"Session initialization complete. Created {sessions_created} sessions.")

if __name__ == "__main__":
    initialize_sessions()
