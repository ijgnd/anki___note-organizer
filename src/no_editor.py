from anki.hooks import wrap
from aqt.editor import Editor

from .config import gc


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


if gc("nids: hide backup field in editor"):
    Editor.setNote = wrap(Editor.setNote, onSetNote, "after") 
