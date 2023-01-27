# hamster 1.53
#
# author: A. Broekema
# created: 2019-12-08
# changed: 2023-01-27


from base64 import b64encode, b64decode
from itertools import cycle
import hashlib
from pathlib import Path
import sys
import os
import json
import time
import ssl
from PyQt6 import QtWidgets, QtGui
from PyQt6.QtCore import QT_VERSION_STR, PYQT_VERSION_STR
from irods.session import iRODSSession
from irods.meta import iRODSMeta
from irods.column import Criterion
# from irods.column import Like
from irods.models import DataObject, DataObjectMeta, Collection, CollectionMeta
from irods.models import User, UserGroup
# from irods.models import CollectionAccess, CollectionUser
# from irods.query import SpecificQuery



# iRODS imports (from: https://github.com/niess/ishell/blob/master/ishell/core.py)
# from irods.exception import (CATALOG_ALREADY_HAS_ITEM_BY_THAT_NAME,
                             # CAT_NAME_EXISTS_AS_COLLECTION,
                             # CollectionDoesNotExist, DataObjectDoesNotExist,
                             # USER_FILE_DOES_NOT_EXIST)
from irods.exception import (CollectionDoesNotExist, DataObjectDoesNotExist,
                             USER_FILE_DOES_NOT_EXIST)


import design   # this file holds the MainWindow and all design related things

# init globals
MY_SESSION   = 0
DICT_DC      = {}     # current form/object
DICT_COPY    = {}
DICT_UNDO    = {}
DICT_HAMSTER = {}   # hamster environment
DICT_IRODS   = {}   # iRODS environment
USER_HOME    = str (Path.home ())
FN_DOT_HAMSTER = ""
FILESIZES = 0
NFILES    = 0
NDIRS     = 0
FILESIZES_SCAN = 0
FILESIZES_SCAN_MB = 0
NFILES_SCAN = 0
NDIRS_SCAN = 0
# init colors
COLOR_FILE_NO_SIDE   = QtGui.QColor ('black')
COLOR_DIR_NO_SIDE    = QtGui.QColor ('blue')
# COLOR_FILE_WITH_SIDE = QtGui.QColor ('green')
# COLOR_DIR_WITH_SIDE  = QtGui.QColor ('purple')


def applog (label, desc):
    "Howto call this method: applog (x, y)"
    print (label + ": \'" + desc + "\'")


def update_dict (dict_this, key, value):
    "Update dict only if len (value) > 0"
    if len (value) > 0:
        dict_this.update ({key : value})


def scan_collections_and_objects (src):
    "src: full path name iRODS collection"
    global MY_SESSION, FILESIZES_SCAN, NFILES_SCAN
    search_tuple = (Collection.name, DataObject.id, DataObject.size)
    search_path = Criterion ('like', Collection.name, src + '%')
    query = MY_SESSION.query (* search_tuple).filter(search_path)
    for result in query:
        NFILES_SCAN += 1
        FILESIZES_SCAN += result[DataObject.size]


def print_statistics (n_files, n_dirs, n_size, n_ticks):
    "comment here"
    print ("%12.1f seconds                          " % n_ticks)
    print ("%12d files" % n_files)
    print ("%12d directories" % n_dirs)
    if n_size < 1024:
        print ("%12d Bytes" % n_size)
    else:
        if n_size < (1024 * 1024):
            print ("%12.1f KB (%d Bytes)" % ((n_size / 1024), n_size))
        else:
            print ("%12.1f MB (%d Bytes)" % ((n_size / 1024 / 1024), n_size))
    if n_ticks > 0:
        print ("%12.1f MB/s" % (n_size / n_ticks / 1024 / 1024))
        print ("%12.1f Mbps" % (n_size / n_ticks / 1024 / 1024 * 10))


def xor_encode (data, mask = 'your default mask here'):
    "comment here"
    xored = ''.join (chr (ord (x) ^ ord (y)) for (x, y) in zip (data, cycle (mask)))
    return b64encode (bytes (xored, 'utf-8')).decode ('utf-8')


def xor_decode (data, mask = 'your default mask here'):
    "comment here"
    data = b64decode (data)
    xored = ''.join (chr (int (x) ^ ord (y)) for x, y in zip (data, cycle (mask)))
    return xored


class HamsterApp (QtWidgets.QMainWindow, design.Ui_MainWindow):
    "comment here"

    def __init__(self, *args, **kwargs):
        "comment here"
        global FN_DOT_HAMSTER, DICT_HAMSTER, DICT_IRODS
        global DICT_DC, DICT_COPY, DICT_UNDO
        global COLOR_FILE_NO_SIDE, COLOR_DIR_NO_SIDE
        global MY_SESSION

        super().__init__(*args, **kwargs)
        # super is used here to allow access to variables, methods etc in design.py
        self.setupUi (self) # this is defined in design.py file automatically
                            # it sets up layout and widgets that are defined

        self.init_menus ()
        self.lineEdit_Header.setText ("No connection")
        # init view
        self.show ()
        # init locals
        self.status_message ("Reading config...")
        dict_cfg = {}
        # read ~/.hamster.json (linux style file name)
        FN_DOT_HAMSTER = os.path.join (USER_HOME, ".hamster.json")
        if os.path.isfile (FN_DOT_HAMSTER):
            with open (FN_DOT_HAMSTER, "r") as file_handle:
                dict_cfg = json.load (file_handle)

        # defaults
        DICT_HAMSTER.update ({'current_collection' : ""})
        DICT_HAMSTER.update ({'current_dataobject' : ""})
        DICT_HAMSTER.update ({'last_open' : USER_HOME})
        DICT_HAMSTER.update ({'last_open_download' : USER_HOME})
        DICT_HAMSTER.update ({'remove_unused_avu_s' : False})
        DICT_HAMSTER.update ({'calculate_checksum' : False})
        DICT_HAMSTER.update ({'use_irods_env' : True})
        # valid values: native | irods_environment | pure_python_ssl
        DICT_HAMSTER.update ({'irods_auth' : "irods_environment"})

        keys = ['current_collection', 'current_dataobject', 'last_open', 'last_open_download',
                'remove_unused_avu_s', 'calculate_checksum', 'use_irods_env', 'irods_auth']
        for key in keys:
            if key in dict_cfg:
                DICT_HAMSTER.update ({key : dict_cfg.get (key)})

        if DICT_HAMSTER ['use_irods_env']:
            try:
                env_file = os.environ['IRODS_ENVIRONMENT_FILE']
            except KeyError:
                env_file = os.path.expanduser ('~/.irods/irods_environment.json')

            if os.path.isfile (env_file):
                with open (env_file, "r") as file_handle:
                    DICT_IRODS = json.load (file_handle)

            if "irods_home" not in DICT_IRODS:
                # zonename/home/username
                update_dict (DICT_IRODS, 'irods_home', "/" + \
                    DICT_IRODS ["irods_zone_name"] + "/home/" + DICT_IRODS ["irods_user_name"])
        else:
            keys = ['irods_user_name', 'irods_host', 'irods_port', 'irods_zone_name', 'irods_home',
                    'irods_authentication_scheme', 'irods_client_server_negotiation',
                    'irods_encryption_algorithm', 'irods_encryption_key_size',
                    'irods_encryption_num_hash_rounds', 'irods_encryption_salt_size',
                    'irods_ssl_ca_certificate_file', 'irods_ssl_verify_server',
                    'irods_client_server_policy']
            for key in keys:
                if key in dict_cfg:
                    DICT_HAMSTER.update ({key : dict_cfg.get (key)})
                    DICT_IRODS.update   ({key : dict_cfg.get (key)})

            key = 'irods_password'
            if key in dict_cfg:
                mask = "cmZzYXJhLm5sMA4GA1UdDwEB/wQEAwIFoDAdBgNVHSUEFjAUBggrBgEFBQcDAQYI"
                pw_cfg = dict_cfg.get (key)
                try:
                    # maybe pw is encoded, try to decode it
                    pw_decoded = xor_decode (pw_cfg, mask)
                except:
                    # if it is not encoded, decoding might fail
                    pw_decoded = "not valid"
                if pw_decoded[:9] == 'decoded::':
                    DICT_HAMSTER [key] = dict_cfg [key]
                    DICT_IRODS [key]   = pw_decoded [9:]
                else:
                    pw_encoded = xor_encode ("decoded::" + dict_cfg [key], mask)
                    DICT_HAMSTER [key] = pw_encoded
                    DICT_IRODS [key]   = dict_cfg [key]

            key = 'irods_home'
            if key not in dict_cfg:
                # zonename/home/username
                if ('irods_zone_name' in DICT_IRODS) and ('irods_user_name' in DICT_IRODS):
                    irods_home = "/" + \
                        DICT_IRODS ["irods_zone_name"] + \
                        "/home/" + \
                        DICT_IRODS ["irods_user_name"]
                    DICT_HAMSTER.update ({key : irods_home})
                    DICT_IRODS.update   ({key : irods_home})
                else:
                    DICT_HAMSTER.update ({key : "/"})
                    DICT_IRODS.update   ({key : "/"})

        self.status_message ("Connecting to server...")

        if DICT_HAMSTER ['irods_auth'] == "native":
            with iRODSSession (
                    host     = DICT_IRODS ["irods_host"],
                    port     = int (DICT_IRODS ["irods_port"]),
                    user     = DICT_IRODS ["irods_user_name"],
                    password = DICT_IRODS ["irods_password"],
                    zone     = DICT_IRODS ["irods_zone_name"]) as MY_SESSION:
                self.status_message ("Connected")
                try:
                    MY_SESSION.collections.get (DICT_HAMSTER.get ('current_collection'))
                except CollectionDoesNotExist:
                    update_dict (DICT_HAMSTER, 'current_collection', DICT_IRODS ["irods_home"])
                self.update_collections_and_dataobjects_view (
                    DICT_HAMSTER.get ('current_collection'))

        if DICT_HAMSTER ['irods_auth'] == "irods_environment":
            # connect with PAM authentication, needed for SURFsara
            ssl_context = ssl.create_default_context (
                purpose = ssl.Purpose.SERVER_AUTH,
                cafile = None,
                capath = None,
                cadata = None)
            ssl_settings = {'ssl_context': ssl_context}
            with iRODSSession (irods_env_file = env_file, **ssl_settings) as MY_SESSION:
                self.status_message ("Connected")
                try:
                    MY_SESSION.collections.get (DICT_HAMSTER.get ('current_collection'))
                except CollectionDoesNotExist:
                    update_dict (DICT_HAMSTER, 'current_collection', DICT_IRODS ["irods_home"])
                self.update_collections_and_dataobjects_view (
                    DICT_HAMSTER.get ('current_collection'))

        if DICT_HAMSTER ['irods_auth'] == "pure_python_ssl":
            ssl_context = ssl.create_default_context (
                purpose = ssl.Purpose.SERVER_AUTH,
                cafile  = DICT_IRODS ["irods_ssl_ca_certificate_file"],
                capath  = None,
                cadata  = None)
            ssl_settings = {
                'client_server_negotiation': DICT_IRODS ["irods_client_server_negotiation"],
                'client_server_policy':      DICT_IRODS ["irods_client_server_policy"],
                'encryption_algorithm':      DICT_IRODS ["irods_encryption_algorithm"],
                'encryption_key_size':  int (DICT_IRODS ["irods_encryption_key_size"]),
                'encryption_num_hash_rounds':int(DICT_IRODS ["irods_encryption_num_hash_rounds"]),
                'encryption_salt_size': int (DICT_IRODS ["irods_encryption_salt_size"]),
                'ssl_context': ssl_context}
            with iRODSSession (
                    host     = DICT_IRODS ["irods_host"],
                    port     = int (DICT_IRODS ["irods_port"]),
                    authentication_scheme = DICT_IRODS ["irods_authentication_scheme"],
                    user     = DICT_IRODS ["irods_user_name"],
                    password = DICT_IRODS ["irods_password"],
                    zone     = DICT_IRODS ["irods_zone_name"],
                    **ssl_settings) as MY_SESSION:
                self.status_message ("Connected")
                try:
                    MY_SESSION.collections.get (DICT_HAMSTER.get ('current_collection'))
                except CollectionDoesNotExist:
                    update_dict (DICT_HAMSTER, 'current_collection', DICT_IRODS ["irods_home"])
                self.update_collections_and_dataobjects_view (
                    DICT_HAMSTER.get ('current_collection'))


    def init_menus (self):
        "init menu's and buttons"
        # menu: File
        self.actionUpload_File.triggered.connect (self.slot_upload_file)
        self.actionUpload_Directory.triggered.connect (self.slot_upload_directory)
        self.actionDownload.triggered.connect (self.slot_download)
        self.actionQuit.triggered.connect (self.slot_quit)

        # menu: Edit
        self.actionUndo.triggered.connect (self.slot_undo)
        self.actionProperties_Object.triggered.connect (self.slot_properties_object)
        self.actionRename.triggered.connect (self.slot_rename)
        self.actionDelete.triggered.connect (self.slot_delete)
        self.actionCopyMetadata.triggered.connect (self.slot_copy_metadata)
        self.actionPasteMetadata.triggered.connect (self.slot_paste_metadata)
        self.actionFind.triggered.connect (self.slot_find)
        self.actionGo_Home.triggered.connect (self.slot_go_home)
        self.actionPrefs.triggered.connect (self.slot_preferences)

        # menu: Help
        self.actionHelp.triggered.connect (self.slot_help)
        self.actioniRODS_system_info.triggered.connect (self.slot_irods_sys_info)
        self.actionAbout.triggered.connect (self.slot_about)

        # buttons
        #self.pushButtonPrevFile.triggered.connect (xxx)
        #self.pushButtonNextFile.triggered.connect (xxx)
        self.pushButtonFind.clicked.connect (self.slot_find)
        self.pushButtonGo.clicked.connect(self.slot_go)

        self.listDirFiles.currentItemChanged.connect (self.slot_index_changed)
        #self.listDirFiles.currentTextChanged.connect (self.slot_text_changed)
        self.listDirFiles.itemDoubleClicked.connect (self.slot_list_item_double_clicked)

        self.lineEdit_Header.setReadOnly (True)
        # self.lineEdit_current_dataobject.setReadOnly (True)
        # self.lineEdit_current_collection.setReadOnly (True)

        # disable some menu items
        self.enable_hamster_menu_items (False)

        # not implemented yet...
        self.actionPrefs.setEnabled (False)
        self.actionHelp.setEnabled (False)


    def slot_upload_file (self):
        "Upload File/Data Object"
        global DICT_HAMSTER
        current_collection = DICT_HAMSTER.get ("current_collection")
        last_open = DICT_HAMSTER.get ("last_open")
        fname, _ = QtWidgets.QFileDialog.getOpenFileName (self, "Choose File to upload", last_open)
        if fname:
            # get path, set last-seen-directory
            last_open = os.path.dirname (fname)
            update_dict (DICT_HAMSTER, 'last_open', last_open)
            newobjectname = current_collection + "/" + os.path.basename (fname)
            filesize = os.path.getsize (fname)
            ticks_start = time.time ()
            self.upload_one_file_to_irods (fname, newobjectname)
            ticks_finish = time.time ()
            ticks_elapsed = ticks_finish - ticks_start
            self.update_collections_and_dataobjects_view (current_collection)
            self.status_message ("Upload file completed")
            if DICT_HAMSTER ['calculate_checksum']:
                self.status_message ("Calculate checksum: ON")
            print_statistics (1, 0, filesize, ticks_elapsed)


    def slot_upload_directory (self):
        "Upload Directory/Collection"
        global FILESIZES, NFILES, NDIRS, FILESIZES_SCAN, NFILES_SCAN, NDIRS_SCAN,FILESIZES_SCAN_MB
        global DICT_HAMSTER
        current_collection = DICT_HAMSTER.get ("current_collection")
        last_open = DICT_HAMSTER.get ("last_open")
        directory = QtWidgets.QFileDialog.getExistingDirectory (self,
            "Choose Directory to upload", last_open)
        if directory:
            last_open = os.path.abspath (directory)
            update_dict (DICT_HAMSTER, 'last_open', last_open)
            FILESIZES = 0
            NFILES = 0
            NDIRS = 0
            FILESIZES_SCAN = 0
            FILESIZES_SCAN_MB = 0
            NFILES_SCAN = 0
            NDIRS_SCAN = 0
            self.status_message ("Scanning...")
            if self.scan_directories_and_files (last_open, True):
                self.status_message ("")
                FILESIZES_SCAN_MB = FILESIZES_SCAN // 1024 // 1024
                msg = "Are you sure to upload:\n\n" + \
                       str (NFILES_SCAN) + " files\n" + \
                       str (NDIRS_SCAN) + " directories\n" + \
                       str(FILESIZES_SCAN_MB) + " MB\n"
                button = QtWidgets.QMessageBox.information (self, \
                                   "Upload Collection", \
                                   msg, \
                                   buttons=QtWidgets.QMessageBox.Ok | QtWidgets.QMessageBox.Cancel)
                if button == QtWidgets.QMessageBox.Ok:
                    ticks_start = time.time ()
                    self.upload_dirs_to_irods (last_open, current_collection)
                    ticks_finish = time.time ()
                    ticks_elapsed = ticks_finish - ticks_start
                    self.update_collections_and_dataobjects_view (current_collection)
                    self.status_message ("Upload files and directories completed")
                    if DICT_HAMSTER ['calculate_checksum']:
                        self.status_message ("Calculate checksum: ON")
                    print_statistics (NFILES, NDIRS, FILESIZES, ticks_elapsed)


    def slot_download (self):
        "comment here"
        global DICT_HAMSTER, FILESIZES, NFILES, NDIRS, FILESIZES_SCAN
        global NFILES_SCAN, NDIRS_SCAN, FILESIZES_SCAN_MB

        FILESIZES = 0
        NFILES = 0
        NDIRS = 0
        FILESIZES_SCAN = 0
        FILESIZES_SCAN_MB = 0
        NFILES_SCAN = 0
        NDIRS_SCAN = 0

        current_collection = DICT_HAMSTER.get ("current_collection")
        last_open_download = DICT_HAMSTER.get ("last_open_download")
        current_dataobject = DICT_HAMSTER.get ("current_dataobject")
        fullpath_name = ""

        if current_dataobject:
            if current_dataobject.endswith ('/'):
                # collection
                if current_dataobject.startswith ('/'):
                    # absolute path, strip trailing '/'
                    fullpath_name = current_dataobject[:-1]
                else:
                    # relative path
                    if current_dataobject == "../":
                        fullpath_name = current_collection
                    else:
                        # relative path, strip trailing '/'
                        fullpath_name = current_collection + "/" + current_dataobject[:-1]
                scan_collections_and_objects (fullpath_name)
            else:
                # data object
                if current_dataobject.startswith ('/'):
                    # data object, absolute path (/zone/bbb/aaa)
                    fullpath_name = current_dataobject
                else:
                    # data object, relative path (aaa)
                    fullpath_name = current_collection + '/' + current_dataobject
                obj = MY_SESSION.data_objects.get (fullpath_name)
                NFILES_SCAN += 1
                FILESIZES_SCAN += obj.size

            FILESIZES_SCAN_MB = FILESIZES_SCAN // 1024 // 1024
            msg = str (NFILES_SCAN) + " files, " + \
                  str (FILESIZES_SCAN_MB) + " MB"
            dst_directory = QtWidgets.QFileDialog.getExistingDirectory (self, \
                                "Save downloaded files (" + msg + ")", \
                                last_open_download)
            if dst_directory:
                last_open_download = os.path.abspath (dst_directory)
                update_dict (DICT_HAMSTER, 'last_open_download', last_open_download)
                self.status_message ("Downloading " + msg)
                ticks_start = time.time ()
                if current_dataobject.endswith ('/'):
                    # collection
                    self.download_collection_from_irods (fullpath_name, last_open_download)
                else:
                    local_file = os.path.join (last_open_download, current_dataobject)
                    self.download_dataobject_from_irods (fullpath_name, local_file)
                ticks_finish = time.time ()
                ticks_elapsed = ticks_finish - ticks_start
                print_statistics (NFILES, NDIRS, FILESIZES, ticks_elapsed)
                self.status_message ("Download completed")


    def download_collection_from_irods (self, src, dst):
        "src: full path name iRODS collection; dst: full path name directory"
        global MY_SESSION, NDIRS
        # create directory for collection
        n_2 = src.rfind ('/')
        newdir = os.path.join (dst, src[n_2+1:])
        try:
            os.mkdir (newdir)
            NDIRS += 1
            b_ok2 = True
        except IOError:
            b_ok2 = False
            self.log_message ("Unable to make directory: '" + newdir + "'")
        if b_ok2:
            try:
                coll = MY_SESSION.collections.get (src)
                # Copy data objects
                for obj in coll.data_objects:
                    newlocal = os.path.join (newdir, obj.name)
                    if b_ok2:
                        b_ok2 = self.download_dataobject_from_irods (obj.path, newlocal)
                # Call collections
                for col in coll.subcollections:
                    if b_ok2:
                        b_ok2 = self.download_collection_from_irods (col.path, newdir)
            except CollectionDoesNotExist:
                b_ok2 = False
                self.log_message ("Collection does not exist: '" + src + "'")
        return b_ok2


    def download_dataobject_from_irods (self, src, dst):
        "buffered download, src: full path name iRODS dataobject; dst: full path name file"
        global MY_SESSION, NFILES, FILESIZES
        b_ok = False
        obj = MY_SESSION.data_objects.get (src)
        with open (dst, "wb+") as f_dst, obj.open ('r') as f_src:
            length = MY_SESSION.data_objects.READ_BUFFER_SIZE
            size_tmp = -1
            if obj.size > length << 1:
                size_tmp = FILESIZES
            while True:
                buf = f_src.read (length)
                if not buf:
                    break
                f_dst.write (buf)
                # SOME_DAY: show a progress bar
                if size_tmp >= 0:
                    size_tmp += length
                    print ("            %d files, %.1f MB" % (NFILES, size_tmp / 1024 / 1024),
                        end = "\r")
            NFILES += 1
            FILESIZES += obj.size
            print ("            %d files, %.1f MB" % (NFILES, FILESIZES / 1024 / 1024), end = "\r")
            b_ok = True  # copy success
        return b_ok


    def zzz_download_dataobject_from_irods (self, src, dst):
        "parallel download, src: full path name iRODS dataobject; dst: full path name file"
        global MY_SESSION, NFILES, FILESIZES
        # parallel download (python-irodsclient >= 1.0.0)
        b_ok = False
        try:
            obj = MY_SESSION.data_objects.get (src, dst)
            NFILES += 1
            FILESIZES += obj.size
            print ("            %d files, %.1f MB" % (NFILES, FILESIZES / 1024 / 1024), end = "\r")
            b_ok = True  # copy success
        except (USER_FILE_DOES_NOT_EXIST, DataObjectDoesNotExist):
            self.log_message ("Error reading dataobject: '" + src + "' or writing: '" + dst + "'")
        return b_ok


    def slot_quit (self):
        "comment here"
        global FN_DOT_HAMSTER, DICT_HAMSTER
        # write/update metadata changes
        selection_fullpath = DICT_HAMSTER.get ("selection_fullpath")
        self.cp_form_to_irods_avu (selection_fullpath)
        # SOME_DAY: when there are many unused AVU's, it takes to long to close Hamster
        #           remove unused avu's
        # write settings to ~/.hamster.json
        with open (FN_DOT_HAMSTER, "w+") as file_handle:
            json.dump (DICT_HAMSTER, file_handle)
        self.close ()


    def slot_undo (self):
        "comment here"
        global DICT_UNDO
        dict_tmp = {}
        self.cp_form_to_dict (dict_tmp)
        self.cp_dict_to_form (DICT_UNDO, True)
        DICT_UNDO = dict_tmp.copy ()


    def slot_properties_object (self):
        "comment here"
        global MY_SESSION, DICT_HAMSTER
        global FILESIZES_SCAN, NFILES_SCAN, FILESIZES_SCAN_MB
        selection_fullpath = DICT_HAMSTER.get ("selection_fullpath")
        object_exists = False
        if selection_fullpath:
            if selection_fullpath.endswith ("/"):
                # collection
                b_is_dataobject = False
                try:
                    obj = MY_SESSION.collections.get (selection_fullpath[:-1])
                    object_exists = True
                except CollectionDoesNotExist:
                    self.log_message ("Collection does not exist: '" + selection_fullpath + "'")
            else:
                # data object
                b_is_dataobject = True
                try:
                    obj = MY_SESSION.data_objects.get (selection_fullpath)
                    object_exists = True
                except DataObjectDoesNotExist:
                    self.log_message ("Data object does not exist: '" + selection_fullpath + "'")
            if object_exists:
                msg = ""
                try:
                    # inspect object (Collection or Dataobject)
                    # print all AVU's
                    msg += "Name: " + selection_fullpath + "\n"

                    if b_is_dataobject:
                        # data object
                        msg += "    Type: Dataobject\n"
                        msg += "    owner_name: " + obj.owner_name + "\n"
                        msg += "    create_time: " + str (obj.create_time) + "\n"
                        msg += "    modify_time: " + str (obj.modify_time) + "\n"
                        msg += "    expiry: " + str (obj.expiry) + "\n"
                        msg += "    checksum: " + str (obj.checksum) + "\n"
                        msg += "    comments: " + str (obj.comments) + "\n"
                        n_size = obj.size
                        if n_size < 1024:
                            msg += "    Size: " + str (n_size) + " bytes\n"
                        else:
                            if  n_size < (1024 * 1024):
                                msg += "    Size: " + \
                                    str (n_size // 1024) + " kB (" + \
                                    str (n_size) + " bytes)\n"
                            else:
                                msg += "    Size: " + \
                                    str (n_size // 1024 // 1024) + " MB (" + \
                                    str (n_size) + " bytes)\n"
                        msg += "\nReplica's:\n"
                        for replica in obj.replicas:
                            msg += "    resource: " + replica.resource_name + "\n"
                            msg += "    number:   " + str (replica.number) + "\n"
                            msg += "    fullname: " + replica.path + "\n"
                            msg += "    status:   " + replica.status + "\n"
                    else:
                        # collection
                        msg += "Type: Collection ("
                        # scan collection and print stats
                        FILESIZES_SCAN = 0
                        NFILES_SCAN = 0
                        scan_collections_and_objects (selection_fullpath[:-1])
                        FILESIZES_SCAN_MB = FILESIZES_SCAN // 1024 // 1024
                        msg += str (NFILES_SCAN) + " files, " + \
                              str (FILESIZES_SCAN_MB) + " MB, " + \
                              str (FILESIZES_SCAN) + " bytes)\n"
                    # data object and/or collection
                    msg += "\nMetadata:\n"
                    for avu in obj.metadata.items ():
                        msg += "    " + avu.name + ": " + avu.value
                        if avu.units:
                            msg += " [" + avu.units + "]"
                        msg += "\n"
                    self.log_message (msg)
                except:
                    self.log_message ("Unable to inspect '" + selection_fullpath + "'")


    def slot_rename (self):
        "comment here"
        global MY_SESSION, DICT_HAMSTER
        current_collection = DICT_HAMSTER.get ("current_collection")
        selection_fullpath = DICT_HAMSTER.get ("selection_fullpath")
        fullpath_name = ""
        new_name = self.lineEdit_current_dataobject.text().strip()
        # TODO check syntax input new_name, never trust user input
        self.lineEdit_current_dataobject.setText (new_name)
        if selection_fullpath:
            if selection_fullpath.endswith ('/'):
                # Collection
                fullpath_name = selection_fullpath[:-1]
                if new_name.startswith ('/'):
                    pass
                else:
                    new_name = current_collection + '/' + new_name
                if new_name.endswith ('/'):
                    new_name = new_name[:-1]
                if fullpath_name != new_name:
                    msg = "Old name:\n" + fullpath_name + "\n\nNew name:\n" + new_name
                    button = QtWidgets.QMessageBox.information (self, \
                                       "Rename Collection", msg, buttons = \
                                       QtWidgets.QMessageBox.Ok | QtWidgets.QMessageBox.Cancel)
                    if button == QtWidgets.QMessageBox.Ok:
                        self.status_message (msg)
                        try:
                            MY_SESSION.collections.move (fullpath_name, new_name)
                            self.update_collections_and_dataobjects_view (current_collection)
                        except:
                            self.log_message ("Unable to rename collection '"+fullpath_name+"'")
            else:
                # data object
                fullpath_name = selection_fullpath
                if new_name.startswith ('/'):
                    pass
                else:
                    new_name = current_collection + '/' + new_name
                if fullpath_name != new_name:
                    msg = "Old name:\n" + fullpath_name + "\n\nNew name:\n" + new_name
                    button = QtWidgets.QMessageBox.information (self, \
                                       "Rename Dataobject", msg, buttons = \
                                       QtWidgets.QMessageBox.Ok | QtWidgets.QMessageBox.Cancel)
                    if button == QtWidgets.QMessageBox.Ok:
                        self.status_message ("Rename " + msg)
                        try:
                            MY_SESSION.data_objects.move (fullpath_name, new_name)
                            self.update_collections_and_dataobjects_view (current_collection)
                        except:
                            self.log_message ("Unable to rename dataobject: '"+fullpath_name+"'")


    def slot_delete (self):
        "comment here"
        global MY_SESSION, DICT_HAMSTER
        global FILESIZES_SCAN, NFILES_SCAN, FILESIZES_SCAN_MB
        current_collection = DICT_HAMSTER.get ("current_collection")
        selection_fullpath = DICT_HAMSTER.get ("selection_fullpath")
        del_coll = ""
        if selection_fullpath:
            if selection_fullpath.endswith ('/'):
                # collection
                del_coll = selection_fullpath[:-1]
                msg = "Delete '" + del_coll + "'\n("
                FILESIZES_SCAN = 0
                NFILES_SCAN = 0
                scan_collections_and_objects (del_coll)
                FILESIZES_SCAN_MB = FILESIZES_SCAN // 1024 // 1024
                msg += str (NFILES_SCAN) + " files, " + \
                      str (FILESIZES_SCAN_MB) + " MB, " + \
                      str (FILESIZES_SCAN) + " bytes)\n"
                # question, information, warning, critical
                button = QtWidgets.QMessageBox.information (self, \
                                   "Delete Collection", msg, buttons = \
                                        QtWidgets.QMessageBox.Ok | QtWidgets.QMessageBox.Cancel)
                if button == QtWidgets.QMessageBox.Ok:
                    self.status_message (msg)
                    try:
                        MY_SESSION.collections.remove (del_coll)
                        if del_coll == current_collection:
                            n_2 = current_collection.rfind ('/')
                            current_collection = current_collection[0:n_2]
                            update_dict (DICT_HAMSTER,
                                'current_collection', current_collection)
                        self.update_collections_and_dataobjects_view (current_collection)
                    except CollectionDoesNotExist:
                        self.log_message ("Unable to delete collection \'" + del_coll + "\'")
            else:
                # data object
                msg = "Delete '" + selection_fullpath + "'"
                button = QtWidgets.QMessageBox.information (self, \
                                   "Delete Dataobject", \
                                   msg, \
                                   buttons=QtWidgets.QMessageBox.Ok | QtWidgets.QMessageBox.Cancel)
                if button == QtWidgets.QMessageBox.Ok:
                    try:
                        self.status_message (msg)
                        # OLD: MY_SESSION.data_objects.unlink (selection_fullpath)
                        MY_SESSION.data_objects.unlink (selection_fullpath, force = True)
                        self.update_collections_and_dataobjects_view (current_collection)
                    except USER_FILE_DOES_NOT_EXIST:
                        self.log_message ("Unable to delete dataobject \'" \
                            + selection_fullpath + "\'")


    def slot_copy_metadata (self):
        "comment here"
        global DICT_COPY
        self.cp_form_to_dict (DICT_COPY)


    def slot_paste_metadata (self):
        "comment here"
        global DICT_COPY, DICT_UNDO
        self.cp_form_to_dict (DICT_UNDO)
        self.cp_dict_to_form (DICT_COPY, True)


    def slot_find (self):
        "Search by metadata"
        global DICT_HAMSTER
        search_line = self.lineEdit_search.text().strip()
        # TODO sanatize search_line, never trust user input
        self.lineEdit_search.setText (search_line)
        self.update_search_results ("%" + search_line + "%")


    def slot_go_home (self):
        "Go Home (iRODS home)"
        global DICT_HAMSTER, DICT_IRODS
        self.lineEdit_current_collection.setText (DICT_IRODS ["irods_home"])
        self.slot_go ()


    def slot_go (self):
        "Change directory - icd"
        global MY_SESSION, DICT_HAMSTER
        new_dir = self.lineEdit_current_collection.text().strip()
        if new_dir.endswith ('/'):
            # strip ending "/" from the string
            new_dir = new_dir[:-1]
        try:
            MY_SESSION.collections.get (new_dir)    # check access rights of new_dir
            current_collection = new_dir
            update_dict (DICT_HAMSTER, 'current_collection', current_collection)
            self.update_collections_and_dataobjects_view (current_collection)
        except:
            self.log_message ("Unable to access collection \'" + new_dir + "\'")


    def slot_preferences (self):
        "comment here"
        # SOME_DAY implement this function


    def slot_help (self):
        "comment here"
        # SOME_DAY implement this function


    def slot_irods_sys_info (self):
        "print system info: users in system (? ienv)"
        global MY_SESSION, DICT_IRODS
        msg = ""
        msg += "iRODS environment:\n"
        msg += "    user: " + MY_SESSION.username + "\n"
        msg += "    host: " + MY_SESSION.host + "\n"
        msg += "    port: " + str (MY_SESSION.port) + "\n"
        msg += "    zone: " + MY_SESSION.zone + "\n"
        msg += "    home: " + DICT_IRODS ["irods_home"] + "\n"
        msg += "    server_version: " + str (MY_SESSION.server_version) + "\n"
        # SOME_DAY: irods home from MY_SESSION

        msg += "\nUsers:\n"
        for res in MY_SESSION.query (User):
            msg += "    " + res[User.name] + " (id: " + str (res[User.id]) + ")\n"
        msg += "\nGroups:\n"
        for res in MY_SESSION.query (UserGroup):
            msg += "    " + res[UserGroup.name] + " (id: " + str (res[UserGroup.id]) + ")\n"
        # print (msg)
        self.log_message (msg)


    def slot_about (self):
        "comment here"
        dialog = QtWidgets.QMessageBox (self)
        dialog.setWindowTitle ("About Hamster")
        s_1 = "Version: 1.53\n"
        s_2 = "Licence: GNU GPL, 2019-2023\n"
        s_3 = "Author: Andries Broekema\n"
        s_4 = "Homepage: https://github.com/andries-b/hamster\n"
        s_5 = "Built with: Python, PyQt " + PYQT_VERSION_STR + ", python-irodsclient\n"
        dialog.setText (s_1 + s_2 + s_3 + s_4 + s_5)
        dialog.show ()


    def slot_index_changed (self, curr_item, prev_item):   # Not an index, i is a QListItem
        "comment here"
        global DICT_HAMSTER
        current_collection = DICT_HAMSTER.get ("current_collection")
        selection_fullpath = DICT_HAMSTER.get ("selection_fullpath")
        if prev_item is not None:
            # print ("slot_index_changed    <<< previous:", prev_item.text())
            self.cp_form_to_irods_avu (selection_fullpath)
        if curr_item is None:
            self.lineEdit_current_dataobject.setText ("")
            self.enable_hamster_menu_items (False)
            current_dataobject = ""
            update_dict (DICT_HAMSTER, 'current_dataobject', "")
            self.clear_form ()
        else:
            # print ("slot_index_changed    >>> current: ", curr_item.text())
            self.enable_hamster_menu_items (True)
            if curr_item.text().startswith ('/'):
                # absolute path
                current_dataobject = curr_item.text()
                selection_fullpath = curr_item.text()

                self.lineEdit_current_dataobject.setText (current_dataobject)
                n_2 = current_dataobject.rfind ('/')
                current_collection = current_dataobject[0:n_2]

                update_dict (DICT_HAMSTER, 'current_dataobject', current_dataobject)
                update_dict (DICT_HAMSTER, 'current_collection', current_collection)
                update_dict (DICT_HAMSTER, 'selection_fullpath', curr_item.text())

                self.lineEdit_current_collection.setText (current_collection)
                self.cp_irods_avu_to_form (selection_fullpath)
            else:
                # relative path
                current_collection = DICT_HAMSTER.get ("current_collection")
                current_dataobject = curr_item.text ()
                if current_dataobject.endswith ("../"):
                    current_dataobject = current_collection + "/"
                    selection_fullpath = current_collection + "/"
                    update_dict (DICT_HAMSTER, 'current_dataobject', current_dataobject)
                    update_dict (DICT_HAMSTER, 'selection_fullpath', selection_fullpath)
                    n_2 = current_collection.rfind ("/")
                    self.lineEdit_current_dataobject.setText (current_collection[n_2+1:] + "/")
                    self.lineEdit_current_collection.setText (current_collection)
                else:
                    update_dict (DICT_HAMSTER, 'current_dataobject', current_dataobject)
                    selection_fullpath = current_collection + "/" + current_dataobject
                    update_dict (DICT_HAMSTER, 'selection_fullpath', selection_fullpath)
                    self.lineEdit_current_dataobject.setText (current_dataobject)
                    self.lineEdit_current_collection.setText (current_collection)
                self.cp_irods_avu_to_form (selection_fullpath)


    def slot_list_item_double_clicked (self, i):
        "comment here"
        global MY_SESSION, DICT_HAMSTER
        current_collection = DICT_HAMSTER.get ("current_collection")
        selection_fullpath = DICT_HAMSTER.get ("selection_fullpath")
        self.cp_form_to_irods_avu (selection_fullpath)

        new_dir = ""
        # clear settings...
        update_dict (DICT_HAMSTER, 'current_dataobject', "")
        update_dict (DICT_HAMSTER, 'selection_fullpath', "")

        if i.text().endswith ("/"):
            # Collection
            if i.text().startswith ('/'):
                # absolute path, strip ending "/" from the string
                new_dir = i.text()[:-1]
            else:
                # relative path, Save form to iRODSavu, them move into new directory,
                if i.text().endswith ("../"):
                    n_2 = current_collection.rfind ("/")
                    new_dir = current_collection[0:n_2]
                else:
                    # strip ending "/" from the string
                    new_dir = current_collection + "/" + i.text()[:-1]
            try:
                MY_SESSION.collections.get (new_dir)    # check access rights of new_dir
                current_collection = new_dir
                update_dict (DICT_HAMSTER, 'current_collection', current_collection)
                self.update_collections_and_dataobjects_view (current_collection)
            except CollectionDoesNotExist:
                self.log_message("Unable to access collection \'" + new_dir + "\'")
        else:
            # data object
            if i.text().startswith("/"):
                # absolute path: open collection that hold this dataobject
                n_2 = i.text().rfind("/")
                new_dir = i.text()[0:n_2]
                try:
                    MY_SESSION.collections.get (new_dir)    # check access rights of new_dir
                    current_collection = new_dir
                    update_dict (DICT_HAMSTER, 'current_collection', current_collection)
                    self.update_collections_and_dataobjects_view (current_collection)
                except CollectionDoesNotExist:
                    self.log_message ("Unable to access collection for dataobject \'" \
                        + i.text() + "\'")
            else:
                # no action on double click, already at the collection (relative path)
                pass


    def enable_hamster_menu_items (self, b_switch):
        "comment here"
        self.actionDownload.setEnabled (b_switch)
        self.actionUndo.setEnabled (b_switch)
        self.actionProperties_Object.setEnabled (b_switch)
        self.actionRename.setEnabled (b_switch)
        self.actionDelete.setEnabled (b_switch)
        self.actionCopyMetadata.setEnabled (b_switch)
        self.actionPasteMetadata.setEnabled (b_switch)


    def scan_directories_and_files (self, this_dir, scan_ok):
        "comment here"
        global FILESIZES_SCAN, NFILES_SCAN, NDIRS_SCAN
        if scan_ok:
            try:
                NDIRS_SCAN += 1
                lst = os.listdir (this_dir)
                for file_name in lst:
                    fullpath_name = os.path.join (this_dir, file_name)
                    if os.path.isfile (fullpath_name):
                        FILESIZES_SCAN += os.path.getsize (fullpath_name)
                        NFILES_SCAN += 1
                    else:
                        if os.path.isdir (fullpath_name):
                            scan_ok = self.scan_directories_and_files (fullpath_name, scan_ok)
            except IOError:
                scan_ok = False
                self.log_message ("Error: unable to scan files/directories in '" + this_dir + "'")
        return scan_ok

    def upload_dirs_to_irods (self, this_dir, irods_collection):
        "comment here"
        global MY_SESSION, FILESIZES, NFILES, NDIRS
        global FILESIZES_SCAN, NFILES_SCAN, NDIRS_SCAN, FILESIZES_SCAN_MB
        new_coll = irods_collection + "/" + os.path.basename (this_dir)
        # TODO check valid iRODS name
        # (e.g. length, valid chars, UTF8, trim leading space, trim trailing space, ...)
        try:
            # print ("Create '" + new_coll + "/'")
            MY_SESSION.collections.create (new_coll)
            NDIRS += 1
        except:
            self.log_message ("Error: unable to create collection '" + new_coll + "'")
            return
        try:
            lst = os.listdir (this_dir)
            num_files_scan = NFILES_SCAN
            num_dirs_scan = NDIRS_SCAN
            tot_size_files_scan = FILESIZES_SCAN
            # no divide by 0
            if num_files_scan == 0:
                num_files_scan = 1
            if num_dirs_scan == 0:
                num_dirs_scan = 1
            if tot_size_files_scan == 0:
                tot_size_files_scan = 1
            for file_name in lst:
                # SOME_DAY: show a progress bar
                perc_f = int((NFILES / num_files_scan) * 100.0)
                perc_d = int((NDIRS / num_dirs_scan) * 100.0)
                perc_s = int((FILESIZES / tot_size_files_scan) * 100.0)
                # perc = int(((NFILES/num_files_scan)*50.0)+((FILESIZES/tot_size_files_scan)*50.0))
                print ("  %d/%d files %d%%   %d/%d directories %d%%   %d/%d MB %d%%" % \
                       (NFILES, num_files_scan, perc_f, \
                        NDIRS, num_dirs_scan, perc_d, \
                        FILESIZES/1024/1024, FILESIZES_SCAN_MB, perc_s), \
                        end = "\r")
                #--------------------------
                fullpath_name = os.path.join (this_dir, file_name)
                if os.path.isfile (fullpath_name):
                    # files / data objects
                    FILESIZES += os.path.getsize (fullpath_name)
                    irods_object = new_coll + "/" + file_name
                    self.upload_one_file_to_irods (fullpath_name, irods_object)
                    NFILES += 1
                else:
                    # directories / collections
                    if os.path.isdir (fullpath_name):
                        dest_collection = new_coll
                        self.upload_dirs_to_irods (fullpath_name, dest_collection)
        except IOError:
            self.log_message ("Error: while uploading from '" + this_dir + "'")


    def upload_one_file_to_irods (self, filename, objectname):
        "comment here"
        global MY_SESSION, DICT_HAMSTER
        try:
            # TODO check valid iRODS name
            # (e.g. length, valid chars, UTF8, trim leading space, trim trailing space, ...)
            MY_SESSION.data_objects.put (filename, objectname)
        except:
            self.log_message ("Error: unable to upload " + filename + " to " + objectname)
            return
        if DICT_HAMSTER.get ("calculate_checksum"):
            try:
                sha = self.calculate_sha256_checksum (filename)
                obj = MY_SESSION.data_objects.get (objectname)
                new_meta = iRODSMeta ('Hamster::checksum', "sha2:" + sha)
                obj.metadata[new_meta.name] = new_meta
            except:
                self.log_message ("Error: unable to calculate checksum of " + filename)


    def calculate_sha256_checksum (self, filename):
        "iRODS checksum is the base64 encoded sha256 checksum"
        sha256_hash = hashlib.sha256 ()
        # init sha with zero length bytearray
        sha256_hash.update (bytearray ())
        try:
            with open (filename, "rb") as file_handle:
                # read and update hash string value in blocks of 4K
                for byte_block in iter (lambda: file_handle.read (4096), b""):
                    sha256_hash.update (byte_block)
        except:
            self.log_message ("Error: unable to calculate checksum of " + filename)
        finally:
            file_handle.close ()
        sha = b64encode(sha256_hash.digest()).decode ('utf-8')
        return sha


    def cp_form_to_dict (self, dict_this):
        "comment here"
        dict_this.clear ()
        update_dict (dict_this,
            'Hamster::contact', self.lineEdit_Hamster_contact.text().strip())

        update_dict (dict_this,
            'dc_DOI', self.lineEdit_dc_doi.text().strip())
        update_dict (dict_this,
            'dc_Title', self.lineEdit_dc_title.text().strip())
        update_dict (dict_this,
            'dc_Creator', self.lineEdit_dc_creator.text().strip())
        update_dict (dict_this,
            'dc_Publisher', self.lineEdit_dc_publisher.text().strip())
        update_dict (dict_this,
            'dc_Publication_year', self.lineEdit_dc_publication_year.text().strip())
        update_dict (dict_this,
            'dc_Resource_type', self.lineEdit_dc_resource_type.text().strip())

        update_dict (dict_this,
            'dc_Subject', self.lineEdit_dc_subject.text().strip())
        update_dict (dict_this,
            'dc_Contributor', self.lineEdit_dc_contributor.text().strip())
        update_dict (dict_this,
            'dc_Dates', self.lineEdit_dc_dates.text().strip())
        update_dict (dict_this,
            'dc_Related_ids', self.lineEdit_dc_related_ids.text().strip())
        update_dict (dict_this,
            'dc_Description', self.lineEdit_dc_description.text().strip())

        update_dict (dict_this,
            'dc_Language', self.lineEdit_dc_language.text().strip())
        update_dict (dict_this,
            'dc_Alternate_ids', self.lineEdit_dc_alternate_ids.text().strip())
        update_dict (dict_this,
            'dc_Sizes', self.lineEdit_dc_sizes.text().strip())
        update_dict (dict_this,
            'dc_Formats', self.lineEdit_dc_formats.text().strip())
        update_dict (dict_this,
            'dc_Version', self.lineEdit_dc_version.text().strip())
        update_dict (dict_this,
            'dc_Funding_reference', self.lineEdit_dc_funding_reference.text().strip())
        update_dict (dict_this,
            'dc_Rights_list', self.lineEdit_dc_rights_list.text().strip())


    def cp_dict_to_form (self, dict_this, b_clear_first):
        "comment here"
        if b_clear_first:
            self.clear_form ()
        for key, value in dict_this.items ():
            # print (key + ": " + value)
            if key == 'Hamster::contact':
                self.lineEdit_Hamster_contact.setText (value)
            if key == 'dc_DOI':
                self.lineEdit_dc_doi.setText (value)
            if key == 'dc_Title':
                self.lineEdit_dc_title.setText (value)
            if key == 'dc_Creator':
                self.lineEdit_dc_creator.setText (value)
            if key == 'dc_Publisher':
                self.lineEdit_dc_publisher.setText (value)
            if key == 'dc_Publication_year':
                self.lineEdit_dc_publication_year.setText (value)
            if key == 'dc_Resource_type':
                self.lineEdit_dc_resource_type.setText (value)
            if key == 'dc_Subject':
                self.lineEdit_dc_subject.setText (value)
            if key == 'dc_Contributor':
                self.lineEdit_dc_contributor.setText (value)
            if key == 'dc_Dates':
                self.lineEdit_dc_dates.setText (value)
            if key == 'dc_Related_ids':
                self.lineEdit_dc_related_ids.setText (value)
            if key == 'dc_Description':
                self.lineEdit_dc_description.setText (value)
            if key == 'dc_Language':
                self.lineEdit_dc_language.setText (value)
            if key == 'dc_Alternate_ids':
                self.lineEdit_dc_alternate_ids.setText (value)
            if key == 'dc_Sizes':
                self.lineEdit_dc_sizes.setText (value)
            if key == 'dc_Formats':
                self.lineEdit_dc_formats.setText (value)
            if key == 'dc_Version':
                self.lineEdit_dc_version.setText (value)
            if key == 'dc_Funding_reference':
                self.lineEdit_dc_funding_reference.setText (value)
            if key == 'dc_Rights_list':
                self.lineEdit_dc_rights_list.setText (value)


    def cp_form_to_irods_avu (self, fname):
        "Copy form to DICT_DC/dict_form, cp dict_form to iRODSavu"
        global DICT_DC
        dict_form = {}
        self.cp_form_to_dict (dict_form)
        if not DICT_DC == dict_form:
            self.cp_dict_to_irods_avu (dict_form, fname)
            DICT_DC = dict_form.copy ()


    def cp_irods_avu_to_form (self, fname):
        "Copy iRODSavu to DICT_DC, cp DICT_DC to form"
        global DICT_DC, DICT_UNDO
        DICT_DC = self.cp_irods_avu_to_dict (fname)
        DICT_UNDO = DICT_DC.copy ()
        self.cp_dict_to_form (DICT_DC, True)


    def cp_irods_avu_to_dict (self, fname):
        "Get metadata from data object or collection"
        global MY_SESSION
        dict_this = {}
        object_exists = True
        if fname.endswith ('/'):
            # collection
            try:
                obj = MY_SESSION.collections.get (fname[:-1])
            except CollectionDoesNotExist:
                object_exists = False
                self.log_message ("Collection does not exist: '" + fname + "'")
        else:
            # data object
            try:
                obj = MY_SESSION.data_objects.get (fname)
            except DataObjectDoesNotExist:
                object_exists = False
                self.log_message ("Dataobject does not exist: '" + fname + "'")
        if object_exists:
            # get metadata from object and put metadata in dict. Note: just AV, not units
            keys = ['Hamster::contact', 'dc_DOI', 'dc_Title', 'dc_Creator', 'dc_Publisher',
                    'dc_Publication_year', 'dc_Resource_type', 'dc_Subject', 'dc_Contributor',
                    'dc_Dates', 'dc_Related_ids', 'dc_Description', 'dc_Language',
                    'dc_Alternate_ids', 'dc_Sizes', 'dc_Formats', 'dc_Version',
                    'dc_Funding_reference', 'dc_Rights_list']
            for key in keys:
                meta = obj.metadata.get_all (key)
                if meta != []:
                    update_dict (dict_this, meta[0].name, meta[0].value)
        return dict_this


    def cp_dict_to_irods_avu (self, dict_this, fname):
        "Update metadata from dict to iRODS-AVU's"
        global DICT_DC, MY_SESSION
        access_to_object = False
        if len (fname) > 0:
            if fname.endswith ('/'):
                # collection
                try:
                    obj = MY_SESSION.collections.get (fname[:-1])
                    access_to_object = True
                except:
                    self.log_message ("Unable to access collection '" + fname + "'")
            else:
                # data object
                try:
                    obj = MY_SESSION.data_objects.get (fname)
                    access_to_object = True
                except:
                    self.log_message ("Unable to access dataobject '" + fname + "'")
            if access_to_object:
                try:
                    # find keys in DICT_DC that are not in dict_this => remove
                    different_keys = DICT_DC.keys() - dict_this.keys()
                    for key in different_keys:
                        # applog (key + " remove", DICT_DC[key])
                        obj.metadata.remove (key, DICT_DC[key])

                    # find keys in dict_this that are not in DICT_DC => add
                    different_keys = dict_this.keys() - DICT_DC.keys()
                    for key in different_keys:
                        # applog (key + " add", dict_this[key])
                        new_meta = iRODSMeta (key, dict_this[key])
                        obj.metadata[new_meta.name] = new_meta

                    # find keys in common of two dictionaries => update only when different values
                    common_keys = DICT_DC.keys() & dict_this.keys()
                    for key in common_keys:
                        if dict_this[key] != DICT_DC[key]:
                            # applog (key + " update", dict_this[key])
                            new_meta = iRODSMeta (key, dict_this[key])
                            obj.metadata[new_meta.name] = new_meta
                except:
                    self.log_message ("Unable to change metadata for '" + fname + "'")


    def clear_form (self):
        "comment here"
        self.lineEdit_Hamster_contact.setText ('')

        self.lineEdit_dc_doi.setText ('')
        self.lineEdit_dc_title.setText ('')
        self.lineEdit_dc_creator.setText ('')
        self.lineEdit_dc_publisher.setText ('')
        self.lineEdit_dc_publication_year.setText ('')
        self.lineEdit_dc_resource_type.setText ('')

        self.lineEdit_dc_subject.setText ('')
        self.lineEdit_dc_contributor.setText ('')
        self.lineEdit_dc_dates.setText ('')
        self.lineEdit_dc_related_ids.setText ('')
        self.lineEdit_dc_description.setText ('')

        self.lineEdit_dc_language.setText ('')
        self.lineEdit_dc_alternate_ids.setText ('')
        self.lineEdit_dc_sizes.setText ('')
        self.lineEdit_dc_formats.setText ('')
        self.lineEdit_dc_version.setText ('')
        self.lineEdit_dc_funding_reference.setText ('')
        self.lineEdit_dc_rights_list.setText ('')


    def update_collections_and_dataobjects_view (self, directory):
        "comment here"
        # view iRODS data objects and collections
        global MY_SESSION
        # Clear list and show directory contents
        self.listDirFiles.clear ()
        self.lineEdit_current_dataobject.setText ("")
        current_dataobject = ""
        update_dict (DICT_HAMSTER, 'current_dataobject', current_dataobject)
        self.lineEdit_current_collection.setText (directory)
        self.clear_form ()
        self.lineEdit_Header.setText ("Collections - Dataobjects")
        try:
            coll = MY_SESSION.collections.get (directory)
            # add "../" on top of the list, if there are levels above,
            # i.e. if most-right / is not on position 0
            n_2 = directory.rfind ('/')
            if n_2 > 0:
                dname = "../"
                color = COLOR_DIR_NO_SIDE
                i = QtWidgets.QListWidgetItem (dname)
                i.setForeground (color)
                self.listDirFiles.addItem (i)

            # show collections
            for col in coll.subcollections:
                #print ("C- " + col.path)
                dname = col.name + '/'
                color = COLOR_DIR_NO_SIDE
                i = QtWidgets.QListWidgetItem (dname)
                i.setForeground (color)
                self.listDirFiles.addItem (i)

            # show data objects
            for obj in coll.data_objects:
                #print (obj.name)
                color = COLOR_FILE_NO_SIDE
                i = QtWidgets.QListWidgetItem (obj.name)
                i.setForeground (color)
                self.listDirFiles.addItem (i)
        except:
            self.log_message ("Collection does not exist: '" + directory + "'")


    def update_search_results (self, searchstr):
        "Show search results"
        global MY_SESSION

        # clear list
        self.listDirFiles.clear ()
        self.lineEdit_current_dataobject.setText ("")
        self.lineEdit_current_collection.setText ("")
        self.clear_form ()
        self.lineEdit_Header.setText ("Search results")
        try:
            # collection search...
            # equivalent to 'imeta qu -C dc_Title like title'
            results = MY_SESSION.query (Collection, CollectionMeta).filter( \
                # Criterion ('=', CollectionMeta.name, 'dc_Title')).filter( \
                Criterion ('like', CollectionMeta.name, 'dc_%')).filter( \
                Criterion ('like', CollectionMeta.value, searchstr))

            # SOME_DAY: remove duplicates, let's assume results are sorted, check this assumption
            prev = -1
            for res in results:
                # print (res[Collection.name],
                #        res[CollectionMeta.name],
                #        res[CollectionMeta.value],
                #        res[CollectionMeta.units])
                if res[Collection.id] != prev:
                    prev = res[Collection.id]
                    dname = res[Collection.name] + '/'
                    color = COLOR_DIR_NO_SIDE
                    i = QtWidgets.QListWidgetItem (dname)
                    i.setForeground (color)
                    self.listDirFiles.addItem (i)

            # data object search...
            # equivalent to 'imeta qu -d dc_Title like title'
            results = MY_SESSION.query (Collection.name, DataObject, DataObjectMeta).filter( \
                Criterion ('like', DataObjectMeta.name, 'dc_%')).filter( \
                Criterion ('like', DataObjectMeta.value, searchstr))

            # SOME_DAY: remove duplicates, let's assume results are sorted, check this assumption
            prev = -1
            for res in results:
                # print (res[DataObject.name],
                #        res[DataObjectMeta.name],
                #        res[DataObjectMeta.value],
                #        res[DataObjectMeta.units])
                if res[DataObject.id] != prev:
                    prev = res[DataObject.id]
                    color = COLOR_FILE_NO_SIDE
                    coll_obj = res[Collection.name] + '/' + res[DataObject.name]
                    i = QtWidgets.QListWidgetItem (coll_obj)
                    i.setForeground (color)
                    self.listDirFiles.addItem (i)
        except:
            self.log_message ("Error with search: '" + searchstr + "'")


    def log_message (self, msg):
        "comment here"
        dialog = QtWidgets.QMessageBox (self)
        dialog.setWindowTitle ("Message")
        dialog.setText (msg)
        dialog.show ()


    def status_message (self, msg):
        "comment here"
        print (msg)
        # SOME_DAY: finish this code
        # self.lineEdit_Status.setText (msg)
        # self.show () OR self.refresh () OR self.update () ???


if __name__ == '__main__':
    app = QtWidgets.QApplication(sys.argv)
    w = HamsterApp()
    app.exec()
