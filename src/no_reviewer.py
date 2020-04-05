"""
This file is part of the Note Organizer add-on for Anki

Copyright: (c) 2017 Glutanimate
           (c) 2020 ijgnd

License: GNU AGPL, version 3 or later; https://www.gnu.org/licenses/agpl-3.0.en.html
"""

from anki.hooks import addHook

import aqt
from aqt import mw

from .config import gc
from .no_consts import *
from .rearranger import Rearranger

menu_entries = [
    {"label": "New Note - &before", "cmd": NEW_NOTE, "offset": 0},
    {"label": "&New Note - after", "cmd": NEW_NOTE, "offset": 1},
    {"label": "D&uplicate Note - before", "cmd": DUPE_NOTE, "offset": 0},
    {"label": "&Duplicate Note - after", "cmd": DUPE_NOTE, "offset": 1},
    {"label": "Duplicate Note (with s&cheduling) - before",
        "cmd": DUPE_NOTE_SCHED, "offset": 0},
    {"label": "Duplicate Note (with &scheduling) - after",
        "cmd": DUPE_NOTE_SCHED, "offset": 1},
]


def addNoteOrganizerActions(web, menu):
    """Add Note Organizer actions to Reviewer Context Menu"""
    if mw.state != "review": # only show menu in reviewer
        return

    menu.addSeparator()
    org_menu = menu.addMenu('&New note...')
    for entry in menu_entries:
        cmd = entry["cmd"]
        offset = entry["offset"] 
        action = org_menu.addAction(entry["label"])
        action.triggered.connect(
            lambda _, c=cmd, o=offset: onReviewerOrgMenu(c, o))


def onReviewerOrgMenu(command, offset):
    """Invoke Rearranger from Reviewer to create new notes"""
    card = mw.reviewer.card
    did = card.odid or card.did # account for dyn decks
    deck = mw.col.decks.nameOrNone(did)
    note = card.note()
    
    search = 'deck:"{}"'.format(deck)
    # glutanimate used: rearrange in context of origin deck
    #   note_pool = mw.col.findNotes(search)
    # Downside: other notes in other decks might have more recent nids than the prior note
    # in the same deck so that the new note is sorted before the other ones. This can't be useful,
    # especially if you view your notes independent of the deck or reorganize them later.
    note_pool = mw.col.db.list("select id from notes") 
    note_pool.sort()
    try:
        idx = note_pool.index(note.id)
    except ValueError: # nid not in deck
        return False
    
    # construct command string that imitates Organizer GUI output
    if command.startswith(NEW_NOTE):
        data = MODEL_SAME
    else:
        data = str(note.id)
    composite = command + ": " + data
    note_pool.insert(idx + offset, composite)
    
    # "start = None" (from glutanimate's version from 2017) changes all nids to more or less
    # the current time when you insert a note before the first note in a deck.
    # This doesn't happen if I insert a new note in the gui at the first position.
    # Symptom: rearranger.adjust_nid_order prints "skipping first nid" when called from the 
    # reviewer for a new note before the first one in the deck whereas from the gui I 
    # get "modifying". 
    # With "start = none" the line "elif start and start != (nid // 1000):" from 
    # rearranger.adjust_nid_order can't be true ...
    # In the gui organizer.updateDate sets start to nid/1000 of the 
    # first = oldest nid so that the "elif ..." evaluates to True ...
    # So here I need to set start to nid//1000 of the oldest nid of the deck instead of None
    # Problem: The first element in the list might be 'New: Same note type as previous' so 
    # I have to iterate.
    for nid in note_pool:
        try:
            timestamp = int(nid) // 1000
        except:
            pass
        else:
            break
    start = timestamp  # deck has at least one note (=the note creating the card reviewed)
    moved = []

    rearranger = Rearranger(card=card)
    res = rearranger.processNids(note_pool, start, moved)

    # display result in browser
    if gc("reviewer: Open Browser"):
        browser = aqt.dialogs.open("Browser", mw)
        browser.form.searchEdit.lineEdit().setText(search)
        browser._onSearchActivated()
        rearranger.selectNotes(browser, res)

if gc("reviewer: Context Menu"):
    addHook("AnkiWebView.contextMenuEvent", addNoteOrganizerActions)
