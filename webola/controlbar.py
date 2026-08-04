from PyQt5.Qt import Qt, QLineEdit, QToolButton, QFileDialog, QStyle, QApplication, QFileInfo, QDir, QComboBox, QCompleter, QSizePolicy, QTimer,\
    QObject, QSpinBox

from webola.buttons    import NoFocusButton, ToolButton
from webola.containers import HBoxContainer, Line
from PyQt5 import QtCore
from webola import database
from webola.utils import have_latex

class FileSelector(QObject):
    do_export = QtCore.pyqtSignal()

    def __init__(self, typ, file='', icon=None):
        QObject.__init__(self)
        self.type   = typ
        path, file  = self.split(file)
        #self.label  = QLabel(label)
        self.edit   = QLineEdit(file)
        self.path   = path
        self.icon   = QToolButton()
        self.buddy  = None
        
        icon = icon or QApplication.style().standardIcon(QStyle.SP_DirIcon)

        self.edit.setEnabled(False)
        self.edit.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.icon.setToolTip('Neue Ausgabedatei wählen')
        self.icon.clicked.connect(self.open_file)
        self.icon.setIcon(icon)

    def split(self, file):
        if file.strip() == "":
            return None, file
        else:
            i = QFileInfo(file)
            if i.suffix().lower() != self.type.lower():
                i = QFileInfo("%s.%s" % (file, self.type))
            return i.path(), i.fileName()
        
    def file(self, dialog=True):
        if self.path is None:
            if dialog:
                return self.open_file()
            else:
                return None
        else:
            info = QFileInfo(QDir(self.path), self.edit.text())
            return info.absoluteFilePath()

    def open_file(self):
        select = "%s Dateien (*.%s)" % (self.type.upper(), self.type.lower()) 
        
        file = self.file(dialog=False) or ""
        name = QFileDialog.getSaveFileName(self.edit, 'Ergebnisliste auswählen ...', file, select)[0]
        
        if name == '':
            return None
        else:
            self.set_filename_and_path(name)
            return self.file(dialog=False)
        
    def set_filename_and_path(self, name):
        if name == '': return None

        self.path, file = self.split(name)
        self.edit.setText(file)
        if self.buddy and self.buddy.path is None:
            file = QFileInfo(file).completeBaseName()
            self.buddy.path = self.path
            self.buddy.edit.setText("%s.%s" % (file, self.buddy.type))
        
        return name

    def add(self, container):
        container.add( self.edit  )
        container.add( self.icon  )
        return self

    def join(self, other):
        self.buddy  = other
        other.buddy = self
        return self

class SearchResult():
    def __init__(self, starter, run):
        self.starter = starter
        self.run     = run 
    
class SearchBox(QLineEdit):
    found = QtCore.pyqtSignal(database.Lauf)

    def __init__(self):
        QLineEdit.__init__(self)
        self.data = None
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setClearButtonEnabled(True)
        self.setPlaceholderText('Suche')
        self.setToolTip('Tipp: Eingabe erst löschen, dann mit ENTER den Fokus deaktivieren.')
        # make sure that completer.activated is processed before self.deactivate
        self.returnPressed.connect(lambda: QTimer.singleShot(0, self.deactivate))
                
    def deactivate(self):
        self.data = None
        self.parent().parent().tabs.setFocus(True)
                    
    def set_data(self, data):
        self.data = data
        completer = QCompleter(sorted(data.keys()), self)
        completer.setCaseSensitivity(Qt.CaseInsensitive)
        completer.setFilterMode(Qt.MatchContains)
        completer.activated.connect(self.show_search)
        self.setCompleter(completer)
        
    def show_search(self, text):
        run = self.data[text]
        self.found.emit(run)
    
    def focusInEvent(self, *args, **kwargs):
        if self.data is None:
            webola = self.parent().parent()
            self.set_data(webola.start_search())
        return QLineEdit.focusInEvent(self, *args, **kwargs)

class NoFocusComboBox(QComboBox):
    def __init__(self, items, tooltip):
        super().__init__()
        self.setFocusPolicy(Qt.NoFocus)
        self.addItems(items)
        #self.setToolTip(tooltip)

        self.currentIndexChanged.connect(lambda: self.setToolTip(tooltip(self)))
        self.setToolTip(tooltip(self))

class NoFocusResultsBox(QSpinBox):
    def __init__(self):
        super().__init__()
        self.setMinimum(0)
        self.setSpecialValueText('--')
        self.setFocusPolicy(Qt.NoFocus)
 
        self.valueChanged.connect(self.update_tooltip)
        self.update_tooltip(self.value())
         
    # do not highlight value after pressing +/-
    def stepBy(self, *args, **kwargs):
        QSpinBox.stepBy(self, *args, **kwargs)
        self.lineEdit().deselect()

class MaxResultsBox(NoFocusResultsBox):
    def __init__(self, typ):
        self.typ = typ
        super().__init__()
        
    def update_tooltip(self, n):
        if n == 0:
            text = f'Bei {self.typ}rennen erhält jede:r Starter:in eine Urkunde.'
        elif n == 1:
            text = f'Bei {self.typ}rennen erhält nur der/die Sieger:in eine Urkunde.'
        else:
            text = f'Bei {self.typ}rennen erhalten nur die Plätze 1-{n} Urkunden.'        
        self.setToolTip(text)
        
class MaxPenaltyBox(NoFocusResultsBox):
    def __init__(self, dsq_ab):
        super().__init__()
        self.setMaximum(50)
        self.setValue  (0 if dsq_ab is None else dsq_ab)
        
    def is_dsq(self, anzahl):
        return anzahl > self.value() > 0  
            
    def update_tooltip(self, n):
        if n == 0:
            self.setToolTip("Es sind beliebig viele Strafen möglich.")
        else:
            self.setToolTip(f"Starter:innen mit {n} oder mehr Strafen werden disqualifiziert.")
        
class ControlBar(HBoxContainer):

    def __init__(self, dsq_ab, args, parent=None):
        HBoxContainer.__init__(self, parent)

        info = {'Einzeln'     : 'einzelne Urkunde für jede/n Starter*in',
                'Einzeln+Team': 'einzelne Urkunden und eine Team-Urkunde',
                'Team'        : 'nur eine Urkunde pro Team'}

        maybe_line = lambda: self.add(Line()) if have_latex() else True

        self.fullscreen = self.add( ToolButton(':/fullscreen', tip='Vollbildmodus umschalten.<br><b>Tipp:</b> Mit Strg-+ und Strg-- kann die Schriftgröße variiert werden.') )
        self.export   = self.add( NoFocusButton('Export' , False ), tooltip='Ergebnisse exportieren' )
        self.xlsx     = FileSelector('xlsx').add(self)
        self.format   = self.add( NoFocusComboBox(['XLSX', 'XLSX+TEX']            , lambda s: f"Beim Export {s.currentText()} exportieren"         ))
        self.template = self.add( NoFocusComboBox(['DM', 'Werder']                , lambda s: f"Verwende '{s.currentText()}'-Template beim Export" ))
        self.mode     = self.add( NoFocusComboBox(['Fehler' , 'Treffer' ]         , lambda s: f"Bei Urkunden '{s.currentText()}' anzeigen"         ))
        self.strafen  = self.add( NoFocusComboBox(['ohne Strafen' , 'mit Strafen'], lambda s: f"Die Urkunden {s.currentText()} ausgeben"  ))
        
        self.maxres_einzel  = self.add( MaxResultsBox('Einzel' ) )
        maybe_line()
        self.maxres_staffel = self.add( MaxResultsBox('Staffel') )
        
        self.staffel  = self.add( NoFocusComboBox( sorted(info.keys())               , lambda s: f"Bei Staffeln {info[s.currentText()]} erzeugen"     ))
        self.teamname = self.add( NoFocusComboBox(['ohne Teamname' , 'mit Teamname' ], lambda s: f"Urkunden {s.currentText()} ausgeben"         ))
        maybe_line()
        self.max_penalty = self.add( MaxPenaltyBox(dsq_ab) )
        maybe_line()
        self.search   = self.add( SearchBox() )
        maybe_line()
        self.exit     = self.add( NoFocusButton('Beenden', lambda: True), tooltip="Programm beenden" )        

        self.format.addItem('XLSX+URKUNDEN')  # native PDF generation, no LaTeX needed
        if have_latex():
            self.format.addItem('XLSX+TEX+PDF')
        else:
            self.template.hide()  # only relevant to the LaTeX-based templates

        self.xlsx.do_export.connect(lambda: self.export.click())
        self.template.currentIndexChanged.connect(self.set_default_parameters)
        self.xlsx.edit.setEnabled(False)
        
        self.set_default_parameters(index=None, args=args)
        
    def set_default_parameters(self, index, args=None):
        if args:
            key = 'DM' if args.dm_mode else 'Werder'
        else:
            key = self.template.currentText()
        if 'DM' in key:
            self.mode    .setCurrentText('Fehler'       )
            self.strafen .setCurrentText('mit Strafen'  )
            self.maxres_einzel .setValue(6)
            self.maxres_staffel.setValue(6)
            self.staffel .setCurrentText('Einzeln'      )
            self.teamname.setCurrentText('ohne Teamname')
        else:
            self.template.setCurrentText(key)
            self.mode    .setCurrentText('Fehler'       )
            self.strafen .setCurrentText('mit Strafen'  )
            self.maxres_einzel .setValue(0)
            self.maxres_staffel.setValue(0)
            self.staffel .setCurrentText('Einzeln'      )
            self.teamname.setCurrentText('mit Teamname')
