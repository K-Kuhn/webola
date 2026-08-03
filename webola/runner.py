from pathlib import Path
from datetime import datetime
from webola.xlsx import xls_export_zielliste
from types import SimpleNamespace
from webola.latex import prepare_latex_export_urkunden, tex_export_zielliste
import subprocess
from PyQt5.Qt import QThread, QTimer, QMessageBox, QIcon
import shutil

class MaxRes():
    def __init__(self, einzel, staffel):
        self.einzel  = einzel
        self.staffel = staffel
        
    def valid(self, team, pos):
        maxval = self.staffel if team.ist_staffel() else self.einzel
        return not maxval or pos <= maxval

class Indicator(QTimer):
    def __init__(self, widget):
        super().__init__()
        self.widget = widget
        self.states = "-\\|/"
        self.state  = 0
        self.timeout.connect(lambda: widget.setText(self.next()))
        self.widget.setEnabled(False)
        self.start(200)
    
    def next(self):
        self.state = (self.state+1) % len(self.states)
        return self.states[self.state]

    def reset(self, text, exporter):
        self.stop()
        self.widget.setEnabled(True)
        self.widget.setText(text)
        self.stop()
        if exporter.error:
            box = QMessageBox(QMessageBox.Critical, 'Export-Fehler', exporter.error)
            box.setWindowIcon(QIcon(":/webola.png"))
            box.exec()

class ExportThread(QThread):
    def __init__(self, to_do):
        super().__init__()
        self.to_do = to_do
        self.error = None
        
    def run(self):
        print(f"--- Export {datetime.now().strftime('%d.%m.%Y %H:%M:%S')} ---")
        self.start_work()
        
    def start_work(self):
        for cmds in self.to_do:
            if len(cmds)==1 and cmds[0].startswith('COPY'):
                a, b = cmds[0].split('|')[1:]
                cmds = ['copy', a, b]
                cmd  = lambda: shutil.copy2(a,b) 
            else:
                cmd  = lambda: subprocess.check_call(cmds,stdout=subprocess.DEVNULL)
            
            print(" ".join(cmds))
            try:
                cmd()
            except Exception as e:
                self.error = f'Der Befehl<br><dd>{" ".join(cmds)}</dd><br>konnte nicht ausgeführt werden:<br><dd>{str(e)}</dd>'
                return

def run_export(wettkampf, tabs, control):
        xlsx    = control.xlsx.file()
        formate = control.format.currentText().split('+')

        if xlsx:
            tex   = Path(xlsx).with_suffix('.tex').relative_to(Path.cwd())
            head  = tabs.sheet.controls.get_header()
            datum = tabs.sheet.controls.date.text()
            datum = f" am {datum}" if datum else ''

            ms   = xls_export_zielliste(wettkampf, xlsx, head+datum, tabs)
            
            if 'TEX' in formate:
                
                to_do  = tex_export_zielliste (wettkampf, tex, head, formate)
                
                to_do += prepare_latex_export_urkunden(Path(xlsx), ms, SimpleNamespace(
                    wettkampf = wettkampf, 
                    formate   = formate, 
                    maxres    = MaxRes(control.maxres_einzel .value(), 
                                       control.maxres_staffel.value()),
                    titel     = head, 
                    datum     = tabs.sheet.controls.date .text(),
                    ort       = tabs.sheet.controls.ort  .text(), 
                    template  = control.template.currentText(), 
                    staffel   = control.staffel .currentText(), 
                    modus     = control.mode    .currentText(), 
                    strafen   = control.strafen .currentText(),
                    teamname  = control.teamname.currentText()))

                if to_do:
                    indicator = Indicator(control.export)
                    exporter  = ExportThread(to_do)
                    exporter.finished.connect(lambda: indicator.reset('Export', exporter))
                    exporter.start()
                    return indicator, exporter

        return None, None