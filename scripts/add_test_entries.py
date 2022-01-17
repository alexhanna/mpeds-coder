

from context import config, database
from models import CanonicalEvent, CanonicalEventLink, CodeEventCreator, RecentEvent, RecentCanonicalEvent, User
import random

def add_canonical_event(coder_id_adj1):
    """ Adds a canonical event and linkages to two candidate events."""

    ## Add event
    ce = database.db_session.query(CanonicalEvent).filter(CanonicalEvent.key == 'Milo_Chicago_2016').first()

    if not ce:
        ce = CanonicalEvent(coder_id = coder_id_adj1, 
            key = 'Milo_Chicago_2016', 
            description = 'This is the main event for the protest against Milo in Chicago in 2016. This is filler text to try to break this part of it. This is filler text to try to break this part of it. This is filler text to try to break this part of it. This is filler text to try to break this part of it.')

        ## commit this first so we can get the ID
        database.db_session.add(ce)
        database.db_session.commit()

    ## get two of the candidate events and store in tables
    cand_events = {6032: {}, 21646: {}}

    for event_id in cand_events.keys():
        for record in database.db_session.query(CodeEventCreator).filter(CodeEventCreator.event_id == event_id).all():
            ## put in a list if it a single valued variable
            if record.variable not in cand_events[event_id]:
                if record.variable not in config.SINGLE_VALUE_VARS:
                    cand_events[event_id][record.variable] = []

            ## store the ID as the single variable if SV
            if record.variable in config.SINGLE_VALUE_VARS:
                cand_events[event_id][record.variable] = record.id
            else: ## else, push into the list
                cand_events[event_id][record.variable].append(record.id)

    ## new list for links
    cels = []

    ## randomly put in single-value'd elements into the canonical event
    for sv in config.SINGLE_VALUE_VARS:
        event_id = random.choice(list(cand_events.keys()))

        ## skip if not in cand_events
        if sv not in cand_events[event_id]:
            continue

        ## add the new CELink
        cels.append(CanonicalEventLink(
                coder_id     = coder_id_adj1, 
                canonical_id = ce.id,
                cec_id       = cand_events[event_id][sv]
            ))

    ## just add in the rest of the data
    for event_id in cand_events.keys():
        for variable in cand_events[event_id].keys():
            
            ## skip because we're ignoring single values
            if variable in config.SINGLE_VALUE_VARS:
                continue

            for value in cand_events[event_id][variable]:
                cels.append(CanonicalEventLink(
                    coder_id     = coder_id_adj1,
                    canonical_id = ce.id,
                    cec_id       = value
                ))

    database.db_session.add_all(cels)
    database.db_session.commit()


def add_recent_events(coder_id_adj1):
    """ Add two recent candidate events. """
    database.db_session.add_all([
        RecentEvent(coder_id_adj1, 6032),
        RecentEvent(coder_id_adj1, 21646)
    ])
    database.db_session.commit()


def add_recent_canonical_events(coder_id_adj1):
    """ Add example canonical event to recent canonical events. """
    ce = database.db_session.query(CanonicalEvent).filter(CanonicalEvent.key == 'Milo_Chicago_2016').first()    

    database.db_session.add(RecentCanonicalEvent(coder_id_adj1, ce.id))
    database.db_session.commit()

def main():
    coder_id_adj1 = database.db_session.query(User).filter(User.username == 'adj1').first().id
    add_canonical_event(coder_id_adj1)

if __name__ == "__main__":
    main()