"""
This file is part of the Note Organizer add-on for Anki

Copyright: (c) 2017 Glutanimate
           (c) 2020- ijgnd 

License: GNU AGPL, version 3 or later; https://www.gnu.org/licenses/agpl-3.0.en.html
"""

from pprint import pprint as pp

from aqt.qt import *
from aqt import mw
from aqt.browser import Browser
from aqt.utils import askUser

from anki.hooks import addHook, wrap
from anki.utils import pointVersion

from .organizer_window import Organizer
from .rearranger import Rearranger
from .config import gc
from .no_consts import *

   
def onBrowserRowChanged(self, current, previous):  # self is browser
    """Sync row position to Organizer"""
    if not self.organizer:
        return
    self.organizer.focusNid(self.card.nid)


def onBrowserNoteDeleted(self, _old):  # self is browser
    """Synchronize note deletion to Organizer"""
    if not self.organizer:
        return _old(self)
    nids = self.selectedNotes()
    if not nids:
        return
    ret = _old(self)
    self.organizer.deleteNids(nids)
    return ret


def onBrowserClose(self, evt):  # self is browser
    """Close with browser"""
    if self.organizer:
        self.organizer.close()


def onReorganize(self):  # self is browser
    """Invoke Organizer window"""
    if self.organizer:
        self.organizer.show()
        return
    
    sel = self.selectedCards()  # 50 is selected_cards
    if sel and len(sel) > 1:
        count = len(sel)
    else:
        count = len(self.model.cards if pointVersion() < 45 else self.table._model._items)
    if gc("general: Card Count Warning") and count > gc("general: Card Count Warning"):
        ret = askUser("Are you sure you want to invoke Note Organizer "
            "on {} cards? This might take a while".format(count),
            title="Note Organizer")
        if not ret:
            return False
    
    self.organizer = Organizer(self)
    self.organizer.show()


def setupMenu(self):
    """Setup menu entries and hotkeys"""
    self.menuOrg = QMenu("&Organizer")
    action = self.menuBar().insertMenu(
                self.mw.form.menuTools.menuAction(), self.menuOrg)
    menu = self.menuOrg
    menu.addSeparator()
    a = menu.addAction('Reorganize Notes...')
    a.setShortcut(QKeySequence(gc("shortcut: Organizer")))
    a.triggered.connect(self.onReorganize)


addHook("browser.setupMenus", setupMenu)
Browser.onReorganize = onReorganize
Browser.organizer = None

if pointVersion() < 45:
    Browser.onRowChanged = wrap(Browser._onRowChanged, onBrowserRowChanged, "after")
else:
    Browser.onRowChanged = wrap(Browser.onRowChanged, onBrowserRowChanged, "after")
# TODO gui_hooks.browser_did_change_row(self)
Browser.closeEvent = wrap(Browser.closeEvent, onBrowserClose, "before")
Browser.deleteNotes = wrap(Browser.deleteNotes, onBrowserNoteDeleted, "around")  # in 50 it's delete_selected_notes
