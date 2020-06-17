import os, sys, argparse, subprocess
from gitignore_parser import parse_gitignore
from inotify_simple import INotify, flags

default_ignorefile = '.dropboxignore'
default_header = '# chipsu/dropboxignore@v1'

parser = argparse.ArgumentParser(description='Dropbox Ignore')
parser.add_argument('-w', dest='watch', action='store_true', default=False, help='Watch for changes (default: False)')
parser.add_argument('-f', dest='force', action='store_true', default=False, help='Continue without ignore file (default: False)')
parser.add_argument('-d', dest='dropbox_dir', default=None, help='Dropbox folder (default: ~/Dropbox)')
parser.add_argument('-i', dest='ignore_file', default=None, help='Ignore file (default: $dropbox_dir/.dropboxignore)')
parser.add_argument('-s', dest='ignore_file_header', default=default_header, help='Ignore file (default: ' + default_header + ')')
parser.add_argument('-v', dest='verbose', action='store_true', default=False, help='Debug info (default: False)')
parser.add_argument('-q', dest='quiet', action='store_true', default=False, help='Be quieter (default: False)')
parser.add_argument('--dry-run', dest='dry_run', action='store_true', default=False, help='Dry-run (default: False)')
args = parser.parse_args()
matches = None

dropbox_dir = os.path.expanduser('~/Dropbox') if args.dropbox_dir is None else args.dropbox_dir

if not os.path.isdir(dropbox_dir):
    print('Dropbox dir', dropbox_dir, 'not found, exiting', file=sys.stderr)
    exit(1)

ignore_file = os.path.join(dropbox_dir, default_ignorefile) if args.ignore_file is None else args.ignore_file
ignore_file_header = args.ignore_file_header
watch = args.watch
force = args.force
verbose = args.verbose
quiet = args.quiet
dry_run = args.dry_run

if verbose:
    print('ignore_file', ignore_file)
    print('ignore_file_header', ignore_file_header)
    print('watch', watch)
    print('force', force)
    print('verbose', verbose)
    print('quiet', quiet)
    print('dry_run', dry_run)

def is_valid_ignorefile():
    if not os.path.isfile(ignore_file):
        return False
    with open(ignore_file) as file:
        if file.readline().strip() == ignore_file_header:
            return True
    print('Ignore file found but header is invalid, first line should be', ignore_file_header, file=sys.stderr)
    return False

def load_ignorefile():
    if is_valid_ignorefile():
        matches = parse_gitignore(ignore_file, dropbox_dir)
    elif force:
        if not quiet: print('Ignore file', ignore_file, 'not found, ignore nothing until it exists')
        matches = None
    else:
        print('Ignore file', ignore_file, 'not found, run with -f to ignore', file=sys.stderr)

def update_ignore_attr(path):
    name = os.path.relpath(path, dropbox_dir)
    ignore = matches is not None and matches(name)
    if verbose or dry_run: print('Ignore path', path, name, ignore)
    if verbose: subprocess.run(['attr', '-l', path])
    if dry_run: return
    #subprocess.run(['attr', '-s', 'com.dropbox.ignored', '-V', str(int(ignore)), path])
    #subprocess.run(['attr', '-q', '-g', 'com.dropbox.ignored', path])
    if ignore: subprocess.run(['attr', '-q', '-s', 'com.dropbox.ignored', '-V', '1', path])
    else: subprocess.run(['attr', '-q', '-r', 'com.dropbox.ignored', path], stderr=subprocess.DEVNULL) # TODO: Maybe check if attr exists instead of silencing stderr

load_ignorefile()

if matches is None and not force:
    exit(1)

for path in os.listdir(dropbox_dir):
    update_ignore_attr(os.path.join(dropbox_dir, path))

if watch:
    inotify = INotify()
    wd_dirs = {}

    if not quiet: print('Waiting for new files in folder', dropbox_dir)
    wd = inotify.add_watch(dropbox_dir, flags.CREATE | flags.DELETE | flags.MODIFY | flags.DELETE_SELF)
    wd_dirs[wd] = dropbox_dir

    ignore_file_dir = os.path.dirname(ignore_file)
    if not os.path.samefile(dropbox_dir, ignore_file_dir):
        if not quiet: print('Waiting for changes for', ignore_file, 'in', ignore_file_dir)
        wd = inotify.add_watch(ignore_file_dir, flags.CREATE | flags.DELETE | flags.MODIFY | flags.DELETE_SELF)
        wd_dirs[wd] = ignore_file_dir

    while True:
        for event in inotify.read(0):
            if verbose:
                print(event)
                for flag in flags.from_mask(event.mask):
                    print('    ' + str(flag))
            if event.wd in wd_dirs:
                path = os.path.join(wd_dirs[event.wd], event.name)
                if os.path.isfile(ignore_file) and os.path.samefile(ignore_file, path):
                    if verbose: print('Ignore file changed, reloading') 
                    load_ignorefile()
                update_ignore_attr(path)
            else:
                print('Unexpected wd', event.wd, 'exiting', file=sys.stderr)
                exit(1)
