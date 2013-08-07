#!/usr/bin/env python
import sys, os, re, tempfile
from copy import deepcopy
sys.path.append('/usr/share/inkscape/extensions')
import inkex
from inkex import NSS

DEBUG = False
KEEPTEMP = False # keep temporary files
OUTPUTPDFMARKS = False # export pdfmarks file (usefull to join many SVG presentation)

try:
    from subprocess import Popen, PIPE
    bsubprocess = True
except:
    bsubprocess = False

class OutputPresentation(inkex.Effect):
    def __init__(self):
        inkex.Effect.__init__(self)
        self.OptionParser.add_option("--directory", action="store",
                                        type="string", dest="directory",
                                        default="~/inkscape-output/",
                                        help="Directory where to save the output.")
        self.OptionParser.add_option("--output", action="store",
                                        type="string", dest="output_name",
                                        default='result',
                                        help="Presentation name")
        self.OptionParser.add_option("--foreground", action="store",
                                        type="string", dest="foreground",
                                        default='foreground',
                                        help="Foreground layer label")
        self.OptionParser.add_option("--background", action="store",
                                        type="string", dest="background",
                                        default='background',
                                        help="Background layer label")
        self.OptionParser.add_option("--title", action="store",
                                        type="string", dest="title",
                                        default='',
                                        help="Presentation title")
        self.OptionParser.add_option("--author", action="store",
                                        type="string", dest="author",
                                        default='',
                                        help="Author name")
        self.OptionParser.add_option("--subject", action="store",
                                        type="string", dest="subject",
                                        default='',
                                        help="Subject")
        self.OptionParser.add_option("--keywords", action="store",
                                        type="string", dest="keywords",
                                        default='',
                                        help="Keywords (separated by ',')")
                                        
    def parse_dir(self, dirname):
        if dirname == '' or dirname == None:
            dirname = './'
        dirname = os.path.expanduser(dirname)
        if not os.path.isdir(dirname):
            os.makedirs(dirname)
        return dirname

    def parse_name(self, name):
        if not os.path.splitext(name)[1] == '.pdf':
            name += '.pdf'
        return name
        
    def effect(self):
        foreground = self.options.foreground
        background = self.options.background
        dirname = self.parse_dir(self.options.directory)
        output_name = os.path.join(dirname, self.parse_name(self.options.output_name))
        tempdir = tempfile.mkdtemp() # to store intermediate files
        pdfmarks_file = os.path.join(tempdir,'pdfmarks')
        pdfmarks = open(pdfmarks_file,'w')

        # Create pdfmarks information
        pdfmarks.write("[ /Title ({0})\n".format(self.options.title))
        if self.options.author != '':
            pdfmarks.write("  /Author ({0})\n".format(self.options.author))
        if self.options.subject != '':
            pdfmarks.write("  /Subject ({0})\n".format(self.options.subject))
        if self.options.keywords != '':
            pdfmarks.write("  /Keywords ({0})\n".format(self.options.keywords))
        pdfmarks.write("  /DOCINFO pdfmark\n")
        pdfmarks.write("[/PageMode /UseOutlines /View [/Fit ] /Page 1 /DOCVIEW pdfmark\n")

        if DEBUG:
            inkex.errormsg("""
                Directory {0}
                Output name {1}
                Temporary directory {2}
                Pdfmarks {3}
            """.format(dirname, output_name, tempdir, pdfmarks_file))

        # Show always visible layer, and parse all the layer
        always_visible = (background, foreground) # list layers always visible
        layer_list = []
        for layer in self.document.xpath('//svg:g[@inkscape:groupmode="layer"]', namespaces=NSS) :
            label = layer.xpath('@inkscape:label', namespaces=NSS)[0]
            if label in always_visible:
                layer.set("style", "display:inline")
            else:
                layer_list.append((label,layer))
                layer.set("style", "display:none")

        i = 0
        anime_pattern_search = re.compile('.*-[0-9]+$')
        anime_pattern_split = re.compile('-[0-9]+$')
        for label, layer in layer_list:
            if DEBUG:
                inkex.errormsg("Parsing layer " + label)
            # Ignore hidden layer, with name starting with '#'
            if '#' == label[0] :
                continue
            # Write bookmarks
            pdfmarks.write("[/Title ({0}) /Page {1} /OUT pdfmark\n".format(label, i+1))
            layer.set("style", "display:inline")

            # Deal with animation, search for layers name .*-[0-9]+$
            # Show all the step smaller than current animation number
            # and store animated (shown) layer in a list
            animated = []
            if re.match(anime_pattern_search, label):
                current_step = int(label.split('-')[-1])
                # label without numbers
                anime = re.split(anime_pattern_split, label)[0]

                current_anime_pattern = re.compile(anime + '\-[0-9]+$')
                for label2, layer2 in layer_list:
                    if re.match(current_anime_pattern, label2):
                        step = int(label2.split('-')[-1])
                        if step < current_step:
                            layer2.set("style", "display:inline")
                            animated.append(layer2)

            # TODO / FIXME
            # Clearing layer would save time, but would need reparsing all
            # the svg element...
            # Not working:
            #for other_layer in layer_dic.itervalues():
                #if not other_layer is layer:
                    #other_layer.clear()

            # FIXME
            # Following is a ugly and very slow hack:
            # Since we cannot call inkscape verbs within extension we have to
            # write, open and export each layer calling (and loading)
            # each time inkscape with the resulting file
            filename = os.path.join(tempdir, label + ".svg")
            self.document.write(filename)

            filename_pdf = os.path.join(tempdir, "export_%03i_" % i + label.replace(' ','_') + ".pdf")
            command = 'inkscape "{0}" --without-gui --export-area-page --export-dpi=300 --export-pdf="{1}"'.format(filename, filename_pdf)
            if bsubprocess:
                p = Popen(command, shell=True, stdout=PIPE, stderr=PIPE)
                return_code = p.wait()
                f = p.stdout
                err = p.stderr
            else:
                _, f, err = os.open3(command)
            f.close()

            if not KEEPTEMP:
                os.remove(filename)

            layer.set("style", "display:none")
            # Hide animated layers
            for layer2 in animated:
                layer2.set("style", "display:none")

            i+=1

        pdfmarks.close()

        # Let's now join the pdf
        command = 'gs -r120 -dBATCH -dNOPAUSE -dPDFSETTINGS=/prepress -dAutoRotatePages=/None -sPAPERSIZE=A4 -sDEVICE=pdfwrite -sOutputFile="{0}" {1}/export_[0-9][0-9][0-9]_*.pdf "{2}"'.format(
                    output_name, tempdir, pdfmarks_file)
        if bsubprocess:
            p = Popen(command, shell=True, stdout=PIPE, stderr=PIPE)
            return_code = p.wait()
            f = p.stdout
            err = p.stderr
        else:
            _, f, err = os.open3(command)
        f.close()

	# Store pdfmarks
	if OUTPUTPDFMARKS:
	    import shutil
	    shutil.move(pdfmarks_file, output_name+'.marks')

        # Clean temps
        if not KEEPTEMP:
            for f in os.listdir(tempdir):
                os.remove(os.path.join(tempdir,f))
            os.removedirs(tempdir)
        else:
            inkex.errormsg('Temporary files stored in %s' % tempdir)

if __name__ == '__main__':
    e = OutputPresentation()
    e.affect(output=False)
