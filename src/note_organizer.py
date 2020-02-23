"""
This file is part of the Note Organizer add-on for Anki

Main Module, hooks add-on methods into Anki

Copyright: (c) Glutanimate 2017
           (c) ijgnd 2020
License: GNU AGPL, version 3 or later; https://www.gnu.org/licenses/agpl-3.0.en.html
"""

from pprint import pprint as pp

from anki.lang import _
import aqt
from aqt.qt import *
from aqt import mw
from aqt.browser import Browser
from aqt.editor import Editor
from aqt.utils import askUser

from anki.hooks import addHook, wrap

from .dialog import Organizer
from .rearranger import Rearranger
from .config import gc
from .consts import *


###### Browser
   
def onBrowserRowChanged(self, current, previous):
    """Sync row position to Organizer"""
    if not self.organizer:
        return
    self.organizer.focusNid(self.card.nid)


def onBrowserNoteDeleted(self, _old):
    """Synchronize note deletion to Organizer"""
    if not self.organizer:
        return _old(self)
    nids = self.selectedNotes()
    if not nids:
        return
    ret = _old(self)
    self.organizer.deleteNids(nids)
    return ret


def onBrowserClose(self, evt):
    """Close with browser"""
    if self.organizer:
        self.organizer.close()


def onReorganize(self):
    """Invoke Organizer window"""
    if self.organizer:
        self.organizer.show()
        return
    
    sel = self.selectedCards()
    if sel and len(sel) > 1:
        count = len(sel)
    else:
        count = len(self.model.cards)
    if gc("general_CARD_COUNT_WARNING") and count > gc("general_CARD_COUNT_WARNING"):
        ret = askUser("Are you sure you want to invoke Note Organizer "
            "on {} cards? This might take a while".format(count),
            title="Note Organizer")
        if not ret:
            return False
    
    self.organizer = Organizer(self)
    self.organizer.show()


def setupMenu(self):
    """Setup menu entries and hotkeys"""
    self.menuOrg = QMenu(_("&Organizer"))
    action = self.menuBar().insertMenu(
                self.mw.form.menuTools.menuAction(), self.menuOrg)
    menu = self.menuOrg
    menu.addSeparator()
    a = menu.addAction('Reorganize Notes...')
    a.setShortcut(QKeySequence(gc("HOTKEY_ORGANIZER")))
    a.triggered.connect(self.onReorganize)


###### Editor

def onSetNote(self, note, hide=True, focus=False):
    """Hide BACKUP_Field if configured"""
    if not self.note or gc("BACKUP_FIELD") not in self.note:
        return
    model = self.note.model()
    flds = self.mw.col.models.fieldNames(model)
    idx = flds.index(gc("BACKUP_FIELD"))
    self.web.eval("""
        // hide last fname, field, and snowflake (FrozenFields add-on)
            document.styleSheets[0].addRule(
                'tr:nth-child({0}) .fname, #f{1}, #i{1}', 'display: none;');
        """.format(idx*2+1, idx))


###### Reviewer

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
    
    # rearrange in context of origin deck
    search = "deck:'{}'".format(deck)
    note_pool = mw.col.findNotes(search)
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
    start = timestamp  # orgin deck has at least one note (=the note creating the card reviewed)
    moved = []

    rearranger = Rearranger(card=card)
    res = rearranger.processNids(note_pool, start, moved)

    # display result in browser
    if gc("REVIEWER_OPEN_BROWSER"):
        browser = aqt.dialogs.open("Browser", mw)
        browser.form.searchEdit.lineEdit().setText(search)
        browser._onSearchActivated()
        rearranger.selectNotes(browser, res)


# Hooks, etc.:

addHook("browser.setupMenus", setupMenu)
Browser.onReorganize = onReorganize
Browser.organizer = None

Browser.onRowChanged = wrap(Browser._onRowChanged, onBrowserRowChanged, "after")
# TODO gui_hooks.browser_did_change_row(self)
Browser.closeEvent = wrap(Browser.closeEvent, onBrowserClose, "before")
Browser.deleteNotes = wrap(Browser.deleteNotes, onBrowserNoteDeleted, "around")

if gc("nids_HIDE_BACKUP_FIELD in editor"):
    Editor.setNote = wrap(Editor.setNote, onSetNote, "after")

if gc("REVIEWER_CONTEXT_MENU"):
    addHook("AnkiWebView.contextMenuEvent", addNoteOrganizerActions)
