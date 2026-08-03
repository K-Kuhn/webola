from webola.utils import time2str, is_linux

import time
from pathlib import Path
from enum import Enum
import codecs
from PyQt5.Qt import QApplication
import re
from webola import exporter
from webola.database import Team
import shutil
import filecmp
from webola.statistik import collect_data

# https://stackoverflow.com/questions/26303293/pyqt-qprogressdialog-shows-but-is-empty-displays-background-content
def nongui(fun):
    """Decorator running the function in non-gui thread while
    processing the gui events."""
    from multiprocessing.pool import ThreadPool

    def wrap(*args, **kwargs):
        pool = ThreadPool(processes=1)
        a_sync = pool.apply_async(fun, args, kwargs)
        while not a_sync.ready():
            a_sync.wait(0.01)
            QApplication.processEvents()
        return a_sync.get()

    return wrap

def init_latex_export(xlsx, key, head):
    base = (xlsx.parent / f"{xlsx.stem}_{key}")
    tex  = base.with_suffix('.tex').relative_to(Path.cwd())
    pdf  = base.with_suffix('.pdf').relative_to(Path.cwd())
    # maybe remove date from head since it will be printed separately
    head = re.sub(r'\s+\d+\.\d+\.\d+$', '', head) 
    
    return tex, pdf, head

def bogenlauf_latex_sty_file():
    #return Path(__file__).parents[1] / 'resources' / 'bogenlauf'
    return 'webola/bogenlauf'

@nongui
def generate_urkunden(xlsx, urkunden,latex_data): 
    
    tex, pdf, head = init_latex_export(xlsx, 'Urkunden', latex_data.titel)

    backup = make_backup(tex)

    with codecs.open(str(tex), 'w', encoding="utf8") as latex:
        prt = lambda msg: latex.write(msg+"\n")
        prt(r'\documentclass{article}')
        prt(r'\usepackage{%s}'   % bogenlauf_latex_sty_file() )
        prt(r'\begin{document}')
        #if latex_data.template == 'DM23':
        #    prt(r'\definecolor{reddish}{HTML}{C45911}') 
        #    prt(r'\color{reddish}')
        
        prt(r'\titel{%s}'        % head               )
        prt(r'\template{%s}'     % latex_data.template)
        prt(r'\datum{%s}'        % latex_data.datum   )
        prt(r'\ort{%s}'          % latex_data.ort     )
        prt(r'\staffelmode{%s}'  % latex_data.staffel )
        prt(r'\fehlermode{%s}'   % latex_data.modus   )
        prt(r'\strafenmode{%s}'  % latex_data.strafen )
        prt(r'\teamnamemode{%s}' % latex_data.teamname)
        latex.writelines(u.tex+"\n" for u in urkunden )
        prt(r'\end{document}')

    return prepare_to_run_latex(tex, backup, pdf, latex_data.formate)

def prepare_to_run_latex(tex,backup,pdf,formats):    
    if 'PDF' in formats:        
        to_do = []
        
        pdffile = tex.with_suffix('.pdf')
        nodiff  = backup is not None and filecmp.cmp(backup, tex, shallow=False)

        if nodiff and pdffile.exists():
            print(f"[INFO] No need to run LaTeX on unchanged file '{tex}' ...")
        else:
            tex_tmp = tex.parent / 'tex-tmp'
            if not tex_tmp.exists():
                tex_tmp.mkdir()
            assert tex_tmp.is_dir()
            
            for _ in range(2):
                # run twice to get background picture right
                to_do.append(['lualatex', '-interaction=batchmode', '-output-directory=%s' % tex_tmp, str(tex)])
            
            tmp = pdf.parent / tex_tmp / Path(pdf.name)
            # copy command differs for Linux/Windows ... correct it later
            to_do.append([f'COPY|{str(tmp)}|{str(pdf)}'])
        
        return to_do
    else:
        return []

@nongui
def generate_medaillenspiegel(xlsx, ms, latex_data):

    tex, pdf, head = init_latex_export(xlsx, 'Medaillenspiegel', latex_data.titel)

    backup = make_backup(tex)

    with codecs.open(str(tex), 'w', encoding="utf8") as latex:
        prt = lambda msg: latex.write(msg+"\n")
        prt(r'\documentclass{article}')
        prt(r'\usepackage{%s}'   % bogenlauf_latex_sty_file())
        prt(r'\usepackage{booktabs}')
        prt(r'\begin{document}')
        prt(r'\titel{%s}'        % head)
        prt(r'\datum{%s}'        % latex_data.datum)
        prt(r'\newcommand{\m}[1]{\makebox[14mm][c]{\textbf{#1}}}')
        prt(r'\vspace*{0.25cm}')
        prt(r'\begin{center}')
        prt(r'\scalebox{1.66}{\Huge Medaillenspiegel} \\[4mm]')
        prt(r'\token[scale=1.0]{titel} \\[4mm]')
        prt(r'\token[scale=0.8]{datum} \\[5mm]')
        prt(r'\Large\renewcommand\arraystretch{1.125}\maybeVShrink{\begin{tabular}{clccc}')
        prt(r'\toprule')
        prt(r'{} & \textbf{Verein}            & \m{Gold} & \m{Silber} & \m{Bronze} \\')
        prt(r'\midrule')

        latex.writelines(e.tex()+"\n" for e in ms.ergebnisse)

        prt(r'\midrule\addlinespace[-0.5ex]')
        prt(r'\multicolumn{2}{l}{\small %d Starter:innen bei %d Meldungen aus %d Vereinen} &' % (ms.starter, ms.meldungen, ms.vereine))
        prt(r'\multicolumn{3}{r}{\small Stand: %s}' % time.strftime("%d. %B %Y, %H:%M Uhr", 
                                                                        time.localtime()))
        prt(r'\end{tabular}}')
        prt(r'\vfill')
        prt(r'\scriptsize\maybeShrink{%s}' % ms.info)
        prt(r'\end{center}')
        prt(r'\end{document}')

    return prepare_to_run_latex(tex, backup, pdf, latex_data.formate)

def path2urkundepdf(path, klasse=None, typ='Urkunden'):
    if path is None: return None
    
    if klasse:
        return (path.parent / (path.stem + '_' + typ + '_' + (klasse.replace(' ','_').replace('/','_')+".pdf"))).relative_to(Path.cwd())
    else:
        return (path.parent / (path.stem + '_' + typ + '.pdf')).relative_to(Path.cwd())

def prepare_latex_export_urkunden(xlsx, ms, latex_data):
    
    to_do = []
    
    pages_for, urkunden = collect_urkunden_data(latex_data)
            
    ms_cmds = generate_medaillenspiegel(xlsx, ms, latex_data)
    u_cmds  = generate_urkunden        (xlsx, urkunden, latex_data)
    
    if 'PDF' in latex_data.formate:        
        to_do.extend(ms_cmds) # call latex to generate Medaillenspiegel
        to_do.extend( u_cmds) # call latex to turn tex into pdf
        
        if is_linux():
            for klasse in sorted(pages_for.keys()):
                QApplication.processEvents()
                pages = ",".join(str(n) for n in pages_for[klasse])
                pdf   = path2urkundepdf(xlsx)
                out   = path2urkundepdf(xlsx, klasse.name)
                if pdf and out:
                    if u_cmds or not out.is_file():
                        to_do.append(['pdfjam','--quiet','--outfile',str(out),str(pdf),pages])

    return to_do

def marker(lauf):
    name = lauf.name
    if name.endswith("'1") or name.endswith("'2"):
        prefix = f'Tag_{name[-1]}_'
        name   = name[:-2]
    else:
        prefix = ""
    
    name = name.replace('/','_').replace(' ','_').replace(':','')
        
    return f"{prefix}{lauf.tab_position+1:02d}_{name}"

class Urkunde():
    zaehler = 0
    
    def __init__(self, team, typ, pos, key, abstand):
        Urkunde.zaehler += 1
        self.nummer = Urkunde.zaehler
        self.team   = team
        name, self.verein = team.get_name_verein()
        self.data = ",".join((
            'pos={%s}'       % (pos if team.is_ranked() else '-'),
            'klasse={%s}'    %  self.texify(key), 
            '%s={%s}'        % (typ, self.texify(name)), 
            'zeit={%s}'      % time2str(team.zeit()), 
            'abstand={%s}'   % abstand, 
            'fehler=%s'      % team.fehler() or 0, 
            'schiessen=%d'   % team.lauf.anzahl_schiessen, 
            'pfeile=%d'      % team.lauf.anzahl_pfeile, 
            'strafen={%s}'   % '',
            'strafzeit={%s}' % team.strafen(sec='sec')))
    
    @staticmethod
    def texify(string):
        return (string.replace('&', r'\&')
                      .replace('$', r'\$')
                      .replace('_', r'\_')
                      .replace('<', r'$<$')
                      .replace('>', r'$>$')
                      .replace('%', r'\%')
                      .replace('°', r'\degree\xspace ')
                      .replace('^', r'\^{}')
                      )
      
class EinzelUrkunde(Urkunde):
    def __init__(self, team, pos, klasse, abstand):
        super().__init__(team, 'name', pos, klasse.name, abstand)      
        self.tex = r'\urkunde{%s,verein={%s}}' % (self.data, self.texify(self.verein))

class StaffelUrkunde(Urkunde):
    def __init__(self, team, pos, klasse, abstand, modus):
        super().__init__(team, 'team', pos, klasse.name, abstand)
        starter  = self.collect_starter()
        self.tex = r'\staffelurkunde{%s,vereine={%s}}{%s}'  % (self.data, self.texify(self.verein), ",".join("{%s}" % s for s in starter))

        if modus == 'Team'          : pass
        elif modus == 'Einzeln'     : self.nummer = self.count_individual_urkunden(len(starter)  )
        elif modus == 'Einzeln+Team': self.nummer = self.count_individual_urkunden(len(starter)+1)
        else:
            raise Exception("Unknown Staffelmode '{modus}' ...")

    def count_individual_urkunden(self,num):
        nummern = [self.nummer + n for n in range(num) ]
        Urkunde.zaehler = nummern[-1]
        return ",".join(str(n) for n in nummern)
        
    def collect_starter(self):
        starter = []
        for s in self.team.liste():
            p = []
            strafen = "" if s.strafen == 0 else f"{s.strafen}x{s.einheit}"
            p.append( "name"     +"={%s}" % self.texify(s.get_name()) )
            p.append( "verein"   +"={%s}" % self.texify(s.verein    ) )
            p.append( "zeit"     +"=%s"   % time2str   (s.zeit()    ) )
            p.append( "fehler"   +"=%d"   % (s.fehler or 0)        )
            p.append( "strafen"  +"={%s}" % strafen )
            p.append( "strafzeit"+"={%s}" % s.strafzeit(sec='sec') )
            starter.append(",".join( p ))
        return starter
        
def collect_urkunden_data(latex_data):

    pages_for = {}  # collect page numbers relevant for each Wertung 
    urkunden  = []  # collect all Urkunden belonging to completed Wertung
    
    Urkunde.zaehler = 0
    
    for klasse in collect_data(latex_data.wettkampf):
        if not klasse.is_wertung_done(): continue

        pos, sieger= 1, None
                
        for team in Team.sortiere(klasse.teams()):
            if team.platz and not team.is_dsq() and latex_data.maxres.valid(team,pos):
                if pos == 1:
                    sieger  = team.zeit()
                    abstand = None
                else:
                    abstand = time2str(team.zeit() - sieger)
                
                if team.ist_staffel():
                    urkunde = StaffelUrkunde(team, pos, klasse, abstand, latex_data.staffel)
                else:
                    urkunde = EinzelUrkunde (team, pos, klasse, abstand)
                
                if klasse not in pages_for:
                    pages_for[klasse] = []
                
                pages_for[klasse].append(urkunde.nummer)
                urkunden.append(urkunde)
                
                pos += 1 if team.is_ranked() else 0

    return pages_for, urkunden
 
class StaffelMode(Enum):
    Off    = 0
    Start  = 1
    Active = 2
 
class TexTableWriter():
    def __init__(self, file, show_results=True):
        self.prnt = lambda msg, end='\n': file.write(str(msg)+end)
        self.row  = None
        self.col  = None
        self.count = 0
        self.show_results = show_results
        self.klasse = None
        self.have_header = False
        self.staffel_mode = StaffelMode.Off

    def start_new_table(self):
        if self.count > 0: 
            self.close_table()
            self.prnt(r'\newpage') 
            
        self.count += 1
            
        if self.staffel_mode != StaffelMode.Off:             
            header  = 'Ergebnisse' if self.show_results else 'Startliste'
            staffel = ' (Staffel)' if self.klasse.ist_staffel() else ''
            self.prnt(r'\fancyhead[L]{\large\bf %s%s\quad -- \quad %s}' % (header, staffel, self.klasse.name))
        
        self.prnt(r'\begin{longtable}{@{\,}l@{\extracolsep{\fill}}cl@{~}l@{~}c@{~}ccc@{~}c@{\,}}')              
                
        self.prnt(r'\multicolumn{9}{r@{\,}}{\footnotesize Stand: %s}' % time.strftime("%d. %B %Y, %H:%M Uhr", time.localtime()))
        self.prnt(r'\endfoot')
        
        if self.staffel_mode != StaffelMode.Off: 
            self.prnt(r'\multicolumn{9}{r@{\,}}{\footnotesize Stand: %s}' % time.strftime("%d. %B %Y, %H:%M Uhr", time.localtime()))
            self.prnt(r'\endlastfoot')        
            if self.show_results:
                self.prnt(r'& & & & & Zeit & Abstand & Fehler\\\midrule')
            else:
                self.prnt(r'\\\midrule')
            self.prnt(r'\endhead')
        
        if self.staffel_mode == StaffelMode.Off: self.prnt(r'\midrule')

        return True

    def print_header(self, text):
        self.prnt(r'\documentclass[12pt]{article}') 
        self.prnt(r'\usepackage{fontspec}')
        self.prnt(r'\setmainfont{Alegreya Sans}') 
        self.prnt(r'\usepackage{lastpage}')
        self.prnt(r'\usepackage[a4paper, %s, headheight=18pt, margin=10mm, top=18mm, headsep=5mm]{geometry}' % ('landscape' if self.show_results else ''))
        self.prnt(r'\usepackage{fancyhdr}')
        self.prnt(r'\fancyhf{}')  
        self.prnt(r'\fancypagestyle{plain}{}') 
        self.prnt(r'\fancyhead[L]{\large\bf %s\quad -- \quad %s}' % ('Ergebnisse' if self.show_results else 'Startliste', text))
        self.prnt(r'\fancyhead[R]{\footnotesize Seite \thepage\ von \pageref{LastPage}}') 
        self.prnt(r'\pagestyle{plain}') 
        self.prnt(r'\usepackage{csquotes}')
        self.prnt(r'\MakeOuterQuote{"}')
        self.prnt(r'\usepackage{longtable}')
        self.prnt(r'\setlength\LTcapwidth{\textwidth}')
        self.prnt(r'\setlength\LTleft{0pt}')
        self.prnt(r'\setlength\LTright{0pt}')
        self.prnt(r'\usepackage{booktabs}')
        self.prnt(r'\setlength{\heavyrulewidth}{\lightrulewidth}')
        self.prnt(r'\setlength{\parindent}{0pt}')
        self.prnt(r'\begin{document}')
        self.prnt(r'\large')
        self.start_new_table()
                
    def print_linebreak(self, c):
        self.col = 1
        staffel = self.staffel_mode == StaffelMode.Active
        if c == 1 or (c==2 and not self.show_results):
            if c==2:
                if staffel:
                    self.prnt(r'\\\midrule')
                else:
                    self.prnt(r'\\\addlinespace[5mm]')
            else:
                self.prnt(r'\\\midrule')
                
            if c==1 and not self.have_header:
                self.prnt(r'\endhead')
                self.have_header = True                    
        else:
            if self.staffel_mode != StaffelMode.Off and c==2:
                self.prnt(r'\\')  #    allow pagebreak
            else:
                self.prnt(r'\\*') # disallow pagebreak
    
    @staticmethod
    def maybe_shorten(text, condition, width):
        if condition and len(text) > width+3:
            stem = text[:width]+r'\ldots'
            m = re.match(r'.*?([IV]+)$', text)
            if m: stem += ' '+m.group(1)       
            return stem
        else:
            return text

    @staticmethod
    def maybe_split(text, condition):
        if condition and '/' in text: # split long combined klasse
            return r'\smash{\begin{tabular}[t]{@{}l@{}}%s\end{tabular}}' % r'\\'.join(text.split('/'))
        else:
            return text 

    @staticmethod
    def maybe_smaller(text, condition):
        if condition:
            return r'\footnotesize '+str(text) 
        else:
            return text 

    @staticmethod
    def use_large(text, bold = False, multi=False):
        if bold:
            latex = r'\Large\textbf{'+str(text)+'}'
        else: 
            latex = r'\Large '+str(text)
        return r"\multicolumn{2}{l}{%s}" % latex if multi else latex

    def cell(self, r, c, text, *args):  
        
        if self.staffel_mode == StaffelMode.Start and self.count > 0:
            self.start_new_table()
            
        if self.row is None and self.col is None:
            assert r == 1 and c == 1
            self.print_header(text)
            self.header_text = text
            self.row  = 3
            self.col  = c
        else:
            if r > self.row and self.staffel_mode != StaffelMode.Start:
                self.print_linebreak(c)
            for _ in range(self.col, c):
                self.prnt(r' & ', end='')

            staffel = self.staffel_mode != StaffelMode.Off
            staffel_header = staffel and c<4 and len(args) <2   
            staffel_body   = staffel and c<5 and len(args)==2
            
            if self.show_results or staffel_header or staffel_body or (not staffel and c<5):
                text = self.maybe_split  (text, c==1)
                text = self.maybe_shorten(text, c==3 and not staffel_header, 21)
                text = self.maybe_shorten(text, c==4, 30)            
                if self.show_results:
                    text = self.maybe_smaller(text, len(args)==2)
                else:                        
                    if staffel_header and c==3:
                        text = self.use_large(text, bold = staffel_header, multi=True)
                        c += 1
                    else:
                        text = self.use_large(text, bold = staffel_header)
                    
                self.prnt(text, end='')
                          
            self.row = r
            self.col = c         
            
        if self.staffel_mode == StaffelMode.Start:
            self.staffel_mode = StaffelMode.Active
            
    def close_table(self):
        self.prnt(r'\\\bottomrule')
        self.prnt(r'\end{longtable}')        

    def finish(self):
        self.close_table() 
        self.prnt(r'\end{document}')        

def make_backup(filename):
    if filename.exists():
        backup = filename.with_suffix('.bak')
        shutil.copy2(filename, backup)
    else:
        backup = None

    return backup

def tex_export_single_zielliste(wettkampf, filename, head, formate, tag):
    if tag is not None:
        filename = Path(f"{filename.with_suffix('')}_Tag_{tag}.tex")
        head     = head + f' \\quad -- \\quad Tag ~ {tag}'
    
    backup = make_backup(filename)
    
    with codecs.open(str(filename), 'w', encoding="utf8") as latex:
        write = TexTableWriter(latex)
        exporter.generic_export(wettkampf, head, write, empty=False, tag=tag)
        write.finish()
        
    return prepare_to_run_latex(filename, backup, filename.with_suffix('.pdf'), formate)

def tex_export_zielliste(wettkampf, filename, head, formate):

    to_do = []
    
    if wettkampf.has_day_markers():
        to_do.extend(tex_export_single_zielliste(wettkampf, filename, head, formate, tag=1))
        to_do.extend(tex_export_single_zielliste(wettkampf, filename, head, formate, tag=2))
    else:
        to_do.extend(tex_export_single_zielliste(wettkampf, filename, head, formate, tag=None))
    
    return to_do

