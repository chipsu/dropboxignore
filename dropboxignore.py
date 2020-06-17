import os, sys, argparse, subprocess, pathspec
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
parser.add_argument('--attr-name', dest='attr_name', default='com.dropbox.ignored', help='Attribute name (default: com.dropbox.ignored)')
parser.add_argument('--attr-zero', dest='attr_zero', action='store_true', default=False, help='Zero attr instead of removing (default: False)')
parser.add_argument('--depth', dest='depth', type=int, default=1, help='Max depth for recursion. 0 = no limit, use with care. (default: 1)')

args = parser.parse_args()
spec = None

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
attr_name = args.attr_name
attr_zero = args.attr_zero
depth = args.depth

if depth == 0:
    # not tested, feel free to remove this and try it out
    print('Unlimited recursion disabled for now')
    exit(1)

if depth != 1 and watch:
    print('Recursive watch not supported yet')
    exit(1)

if verbose:
    print('ignore_file', ignore_file)
    print('ignore_file_header', ignore_file_header)
    print('watch', watch)
    print('force', force)
    print('verbose', verbose)
    print('quiet', quiet)
    print('dry_run', dry_run)
    print('attr_name', attr_name)
    print('attr_zero', attr_zero)
    print('depth', depth)

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
        if not quiet: print('Loading ignore file', ignore_file)
        with open(ignore_file, 'r') as fh:
            return pathspec.PathSpec.from_lines('gitwildmatch', fh)
    elif force:
        if not quiet: print('Ignore file', ignore_file, 'not found, ignore nothing until it exists')
    else:
        print('Ignore file', ignore_file, 'not found, run with -f to ignore', file=sys.stderr)
    return None

def update_ignore_attr(path):
    ignore = spec is not None and spec.match_file(path)
    if verbose or dry_run: print(int(ignore), os.path.relpath(path, dropbox_dir))
    if verbose: subprocess.run(['attr', '-l', path])
    if dry_run: return ignore
    if zero_attr:
        subprocess.run(['attr', '-s', attr_name, '-V', str(int(ignore)), path])
    else:
        if ignore: subprocess.run(['attr', '-q', '-s', attr_name, '-V', '1', path])
        else: subprocess.run(['attr', '-q', '-r', attr_name, path], stderr=subprocess.DEVNULL) # TODO: Maybe check if attr exists instead of silencing stderr
    return ignore

def update_ignore_dir(dir, level = 1):
    for path in os.listdir(dir):
        full = os.path.join(dir, path)
        ignore = update_ignore_attr(full)
        if ignore or not os.path.isdir(full):
            continue
        if depth == 0 or level < depth:
            if verbose: print('Recurse', full, depth)
            update_ignore_dir(full, level + 1)

spec = load_ignorefile()

if spec is None and not force:
    exit(1)

update_ignore_dir(dropbox_dir)

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
                    spec = load_ignorefile()
                update_ignore_attr(path)
            else:
                print('Unexpected wd', event.wd, 'exiting', file=sys.stderr)
                exit(1)
