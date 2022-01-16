"""
This file is part of the Note Organizer add-on for Anki

Copyright: (c) 2017 Glutanimate
           (c) 2020- ijgnd

License: GNU AGPL, version 3 or later; https://www.gnu.org/licenses/agpl-3.0.en.html
"""

# from timeit import default_timer as timer
from pprint import pprint as pp

from anki.hooks import addHook, remHook

from aqt.qt import *
from aqt.utils import (
    saveHeader, 
    restoreHeader, 
    saveGeom,
    restoreGeom,
    askUser,
    tooltip
)

if qtmajor == 5:
    from .forms5 import organizer  # type: ignore  # noqa
else:
    from .forms6 import organizer  # type: ignore  # noqa

from .custom_table_widget import NoteTable
from .rearranger import Rearranger
from .config import anki_21_version, gc
from .no_consts import *


class Organizer(QDialog):
    """Main dialog"""
    def __init__(self, browser):
        super(Organizer, self).__init__(parent=browser)
        self.browser = browser
        self.mw = browser.mw
        self.dialog = organizer.Ui_Dialog()
        self.dialog.setupUi(self)
        self.table = NoteTable(self)
        self.hh = self.table.horizontalHeader()
        self.dialog.tableLayout.addWidget(self.table)
        self.oldnids = []
        self.clipboard = []
        self.modified = False
        self.setupUi()
        addHook("reset", self.onReset)


    def setupUi(self):
        # print("=====Performance benchmark=====")
        # start = timer()
        self.fillTable()
        # end = timer()
        # print("total", end - start)    
        self.setupDate()
        self.updateDate()
        self.setupHeaders()
        restoreGeom(self, "organizer")
        self.setupEvents()
        self.table.setFocus()
        # focus currently selected card:
        if self.browser.card:
            self.focusNid(str(self.browser.card.nid))


    def setupEvents(self):
        """Connect event signals to slots"""
        self.table.selectionModel().selectionChanged.connect(self.onRowChanged)
        self.table.cellChanged.connect(self.onCellChanged)
        self.dialog.buttonBox.rejected.connect(self.onReject)
        self.dialog.buttonBox.accepted.connect(self.onAccept)

        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self.onTableContext)

        s = QShortcut(QKeySequence(gc("shortcut: Insert")),
                self.table, activated=self.onInsertNote)
        s = QShortcut(QKeySequence(gc("shortcut: Dupe")),
                self.table, activated=self.onDuplicateNote)
        s = QShortcut(QKeySequence(gc("shortcut: Dupe (Sched)")),
                self.table, activated=lambda: self.onDuplicateNote(sched=True))
        s = QShortcut(QKeySequence(gc("shortcut: Remove")),
                self.table, activated=self.onRemoveNotes)
        s = QShortcut(QKeySequence(gc("shortcut: Cut")),
                self.table, activated=self.onCutRow)
        s = QShortcut(QKeySequence(gc("shortcut: Paste")),
                self.table, activated=self.onPasteRow)

        # Sets up context sub-menu and hotkeys for various note types
        self.models_menu = self.setupModels()


    def setupDate(self):
        """Set up datetime range"""
        qtime = QDateTime()
        qtime.setTime_t(0)
        self.dialog.date.setMinimumDateTime(qtime)
        self.dialog.date.setMaximumDateTime(QDateTime.currentDateTime())


    def setupModels(self):
        models = [mod['name'] for mod in self.mw.col.models.all()]
        models.sort()
        mm = QMenu("New note...")
        for idx, model in enumerate(models):
            label = model
            if idx < 10:
                modifier = "Ctrl"
            elif idx < 20:
                modifier = "Ctrl+Shift"
            elif idx < 30:
                modifier = "Ctrl+Alt+Shift"
            else:
                modifier = None
            if modifier:
                hotkey = "{}+{}".format(modifier, str((idx+1) % 10))
                label = label + "\t" + hotkey
                sc = QShortcut(QKeySequence(hotkey), 
                    self.table, activated=lambda a=model: self.onInsertNote(a))
            a = mm.addAction(label)
            a.triggered.connect(lambda _, a=model: self.onInsertNote(a))
        return mm


    def setupHeaders(self):
        """Restore and setup headers"""
        self.hh.setSectionsMovable(True)
        self.hh.setSectionsClickable(False)
        self.hh.setHighlightSections(False)
        self.hh.setMinimumSectionSize(50)
        self.hh.setDefaultSectionSize(100)
        self.hh.setSectionResizeMode(QHeaderView.Interactive)
        self.hh.setStretchLastSection(True)
        self.hh.resizeSection(self.hh.logicalIndex(0), 120)
        self.hh.resizeSection(self.hh.logicalIndex(1), 240)
        restoreHeader(self.hh, "organizer")
        vh = self.table.verticalHeader()
        vh.setSectionsClickable(False)
        vh.setSectionResizeMode(QHeaderView.Fixed)
        vh.setDefaultSectionSize(24)
        vh_font = vh.font()
        vh_font.setPointSize(10)
        vh.setFont(vh_font)


    def fillTable(self):
        if anki_21_version <= 44:
            headers, row_contents_list_of_lists = self.gather_contents_old()
        else:
            headers, row_contents_list_of_lists = self.gather_contents_new()

        self.oldnids = [i[0] for i in row_contents_list_of_lists]
        
        row_count = len(row_contents_list_of_lists)
        self.table.setRowCount(row_count)
        self.table.setColumnCount(len(headers))
        self.table.setHorizontalHeaderLabels(headers)

        for row, columns in enumerate(row_contents_list_of_lists):
            for col, value in enumerate(columns):
                if isinstance(value, int) and value > 2147483647:
                    value = str(value)
                item = QTableWidgetItem(value)
                font = QFont()
                # f.setFamily(browser.mw.fontFamily)
                #f.setPixelSize(browser.mw.fontHeight)
                item.setFont(font)
                self.table.setItem(row,col,item)

        self.setWindowTitle("Reorganize Notes ({} notes shown)".format(row_count))


    def gather_contents_old(self):
        """Fill table rows with data"""
        browser = self.browser
        b_t_model = browser.model

        row_contents_list_of_lists = []
        b_t_m_active_cols = b_t_model.activeCols

        # either get selected cards or entire view
        sel_cids_in_b = browser.selectedCards()
        if sel_cids_in_b and len(sel_cids_in_b) > 1:
            # need to map nids to actually selected row indexes
            idxs = browser.form.tableView.selectionModel().selectedRows()
        else:
            sel_cids_in_b = b_t_model.cards
            idxs = None

        # eliminate duplicates, get data, and sort it by nid
        nids_processed = []
        for row, cid in enumerate(sel_cids_in_b):
            if idxs:
                row = idxs[row].row()
            card = b_t_model.cardObjs.get(cid, None)
            if not card:
                card = b_t_model.col.getCard(cid)
                b_t_model.cardObjs[cid] = card
            nid = card.note().id
            if nid in nids_processed:
                continue
            contents_one_row = [str(nid)]
            for col in range(len(b_t_m_active_cols)):
                index = b_t_model.index(row, col)
                contents_one_row.append(b_t_model.data(index, Qt.ItemDataRole.DisplayRole))
            nids_processed.append(nid)
            row_contents_list_of_lists.append(contents_one_row)
        row_contents_list_of_lists.sort()
        """
        row_contents_list_of_lists could look like this if two notes are selcted in the browser table
        if in the browser there are three columns shown
            [
                [nid1, content_cell_1, content_cell_2, content_cell_3],
                [nid2, content_cell_1, content_cell_2, content_cell_3],
            ]
        """

        # after uninstall of advanced browser there are might be unknown columns in b_t_m_active_cols like 
        # my "overdueivl"
        coldict = dict(browser.columns)
        headers = ["Note ID"] + [coldict.get(key, "Add-on") for key in b_t_m_active_cols]

        return headers, row_contents_list_of_lists


    def gather_contents_new(self):
       pass

    def onCellChanged(self, row, col):
        """Update datetime display when (0,0) changed"""
        if row == col == 0 and not (self.mw.app.keyboardModifiers() & Qt.KeyboardModifier.ShiftModifier):
            self.updateDate()


    def updateDate(self):
        """Update datetime based on (0,0) value"""
        item = self.table.item(0, 0)
        if not item:
            return False
        try:
            nid = int(item.text())
        except ValueError:
            return False
        timestamp = nid // 1000
        qtime = QDateTime()
        qtime.setTime_t(timestamp)  # this qt function is obsolete - https://doc.qt.io/qt-5/qdatetime-obsolete.html#setTime_t
        # qtime.setSecsSinceEpoch(timestamp)
        self.dialog.date.setDateTime(qtime)


    def getDate(self):
        """Get datetime"""
        qtime = self.dialog.date.dateTime()
        if not qtime.isValid():
            return None
        timestamp = qtime.toTime_t()  # this qt function is obsolete - https://doc.qt.io/qt-5/qdatetime-obsolete.html#toTime_t
        # timestamp = qtime.toSecsSinceEpoch()
        return timestamp


    def onTableContext(self, pos):
        """Custom context menu for the table"""
        # need to map to viewport due to QAbstractScrollArea:
        gpos = self.table.viewport().mapToGlobal(pos)
        m = QMenu()
        
        a = m.addAction("Cut\t{}".format(gc("shortcut: Cut")))
        a.triggered.connect(self.onCutRow)
        if self.clipboard:
            a = m.addAction("Paste\t{}".format(gc("shortcut: Paste")))
            a.triggered.connect(self.onPasteRow)

        a = m.addAction("New note\t{}".format(gc("shortcut: Insert")))
        a.triggered.connect(self.onInsertNote)

        a = m.addAction("Duplicate note\t{}".format(gc("shortcut: Dupe")))
        a.triggered.connect(self.onDuplicateNote)

        a = m.addAction(
            "Duplicate note (with scheduling)\t{}".format(gc("shortcut: Dupe (Sched)")))
        a.triggered.connect(lambda: self.onDuplicateNote(sched=True))

        m.addMenu(self.models_menu)

        a = m.addAction("Remove\t{}".format(gc("shortcut: Remove")))
        a.triggered.connect(self.onRemoveNotes)

        m.exec_(gpos)


    def onInsertNote(self, model=None):
        """Insert marker for new note"""
        rows = self.table.getSelectedRows()
        if not rows:
            return
        row = rows[0] + 1
        self.table.insertRow(row)
        if not model:
            model = MODEL_SAME
        data = "{}: {}".format(NEW_NOTE, model)
        item = QTableWidgetItem(data)
        font = item.font()
        font.setBold(True)
        item.setFont(font)
        item.setForeground(Qt.GlobalColor.darkGreen)
        self.table.setItem(row, 0, item)
        self.modified = True


    def onDuplicateNote(self, sched=False):
        """Insert marker for duplicated note"""
        rows = self.table.getSelectedRows()
        if not rows:
            return
        row = rows[0]
        new_row = row+1
        self.table.insertRow(new_row)
        marker = DUPE_NOTE if not sched else DUPE_NOTE_SCHED
        for col in range(self.table.columnCount()):
            if col == 0:
                value = self.table.item(row, 0).text()
                nid = ''.join(i for i in value if i.isdigit())
                if value.startswith(DEL_NOTE) or not nid:
                    self.table.removeRow(new_row)
                    return
                data = "{}: {}".format(marker, nid)
                dupe = QTableWidgetItem(data)
                font = dupe.font()
                font.setBold(True)
                dupe.setFont(font)
                dupe.setForeground(Qt.GlobalColor.darkBlue)
            else:
                dupe = QTableWidgetItem(self.table.item(row, col))
            self.table.setItem(new_row, col, dupe)
        self.modified = True


    def onRemoveNotes(self):
        """Remove empty row(s)"""
        rows = self.table.getSelectedRows()
        if not rows:
            return
        to_remove = []
        delmark = "{}: ".format(DEL_NOTE)
        for row in rows:
            item = self.table.item(row, 0)
            if not item:
                continue
            value = item.text()
            # New notes:
            if value.startswith((NEW_NOTE, DUPE_NOTE)): # remove
                to_remove.append(row)
                continue
            # Existing notes:
            if value.startswith(delmark): # remove deletion mark
                new = value.replace(delmark, "")
                item.setText("{}".format(new))
                font = item.font()
                font.setBold(False)
                item.setFont(font)
                item.setForeground(QBrush())
            else: # apply deletion mark
                item.setText("{}: {}".format(DEL_NOTE, value))
                font = item.font()
                font.setBold(True)
                item.setFont(font)
                item.setForeground(Qt.GlobalColor.darkRed)
        for row in to_remove[::-1]: # in reverse to avoid updating idxs
            self.table.removeRow(row)
        self.modified = True


    def onCutRow(self):
        """Store current selection in clipboard"""
        rows = self.table.getSelectedRows()
        if not rows:
            return
        self.clipboard = rows


    def onPasteRow(self):
        """Paste current selection"""
        # TODO: Needs some refactoring

        t = self.table
        cut = self.clipboard
        if not self.clipboard:
            return
        
        rows = self.table.getSelectedRows()
        if not rows:
            return
        
        new_row = rows[0]
        if new_row == cut[0] or new_row in range(cut[0], cut[-1]+1):
            # return if source and target identical
            # FIXME: support pasting back into the same range
            return False

        # Insert new row and copy data over
        offset = 0
        cols = t.columnCount()
        select = []
        for cut_row in cut[::-1]:
            t.insertRow(new_row)
            if new_row < cut_row:
                offset += 1
            adj_row = cut_row + offset
            # print("moving {} (actual: {}) to {}".format(
            #         cut_row+1, adj_row+1, new_row+1))
            for col in range(cols):
                dupe = QTableWidgetItem(t.item(adj_row, col))
                font = dupe.font()
                font.setBold(True)
                dupe.setFont(font)
                t.setItem(new_row, col, dupe)
                if col == 0:
                    value = dupe.text()
                    if value not in t.moved:
                        t.moved.append(value)
            t.clearSelection()

        # Remove old row
        for row in cut[::-1]:
            # print("removing {}".format(row+offset))
            t.removeRow(row+offset)

        # reselect moved rows
        selectionModel = t.selectionModel()
        if new_row > cut[0]:
            index1 = t.model().index(new_row-len(cut), 0)
            index2 = t.model().index(new_row-1, 2)
        else:
            index1 = t.model().index(new_row, 0)
            index2 = t.model().index(new_row+len(cut)-1, 0)
        itemSelection = QItemSelection(index1, index2)
        selectionModel.select(itemSelection, 
            QItemSelectionModel.Rows | QItemSelectionModel.Select)

        self.clipboard = None


    def onRowChanged(self, current, previous):
        """Sync row change to Browser"""
        mods = QApplication.keyboardModifiers()
        if mods & (Qt.KeyboardModifier.ShiftModifier | Qt.KeyboardModifier.ControlModifier):
            return # don't try to focus when multiple items are selected
        rows = self.table.getSelectedRows()
        if not rows:
            return
        item = self.table.item(rows[0], 0)  # PyQt5.QtWidgets.QTableWidgetItem
        if not item:
            return
        nid = item.text()
        if ": " in nid: # ignore action markers
            nid = nid.split(": ")[1]
        cids = self.mw.col.db.list(
                "select id from cards where nid = ? order by ord", nid)
        for cid in cids:
            if cid in self.browser.model.cards:
                self.browser.focusCid(cid)
                break


    def deleteNids(self, nids):
        """Find and delete row by note ID"""
        for nid in nids:
            nid = str(nid)
            cells = self.table.findItems(nid, Qt.MatchFlag.MatchEndsWith)
            if cells:
                row = cells[0].row()
                self.table.removeRow(row)


    def focusNid(self, nid):
        """Find and select row by note ID"""
        nid = str(nid)
        cells = self.table.findItems(nid, Qt.MatchFlag.MatchEndsWith)
        if cells:
            self.table.setCurrentItem(cells[0])


    def onReset(self):
        self.clipboard = []
        self.fillTable()
        self.updateDate()
        if self.browser.card:
            self.focusNid(str(self.browser.card.nid))


    def cleanup(self):
        remHook("reset", self.onReset)
        self.browser.organizer = None
        saveGeom(self, "organizer")
        saveHeader(self.hh, "organizer")


    def reject(self):
        """Notify browser of close event"""
        if self.modified or self.table.moved:
            rej = askUser("Close and lose current changes?",
                title="Note Organizer")
            if not rej:
                return
        self.cleanup()
        super(Organizer, self).reject()


    def onAccept(self):
        """Ask for confirmation, then call rearranger"""
        newnids = []
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if not item: # should not happen
                continue
            newnids.append(item.text())

        if newnids == self.oldnids:
            self.close()
            tooltip("No changes performed")
            return False

        moved = []
        for i in self.table.moved:
            try:
                moved.append(int(i))
            except ValueError: # only add existing notes to moved
                pass

        nn = newnids
        to_delete = len([i for i in nn if i.startswith(DEL_NOTE)])
        to_add = len([i for i in nn if i.startswith((NEW_NOTE, DUPE_NOTE))])
        to_move = len(moved)

        if not gc("general: ask confirmation"):
            pass
        else:
            ret = askUser("Overview of <b>changes</b>:"
                "<ul style='margin-left: 0'>"
                "<li><b>Move</b> at least <b>{}</b> note(s)</li>"
                "<li><b>Remove {}</b> note(s)</li>"
                "<li><b>Create {}</b> new note(s)</li></ul>"
                "Additional notes might have to be updated "
                "to allow for the changes above.<br><br>"
                "Are you sure you want to <b>proceed</b>?".format(to_move, to_delete, to_add),
                parent=self, defaultno=True, title="Please confirm action")
            if not ret:
                return False
          
        start = self.getDate() # TODO: identify cases where only date modified
        repos = self.dialog.cbRepos.isChecked()

        rearranger = Rearranger(browser=self.browser)
        rearranger.processNids(newnids, start, moved, repos=repos)

        self.cleanup()
        super(Organizer, self).accept()


    def onReject(self):
        self.close()
