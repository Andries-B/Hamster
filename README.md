# Hamster is a client application and metadata editor for iRODS systems
Hamster is a client application to iRODS systems with a userfriendly GUI.
It brings the functionality of some iRODS-icommands to the graphical desktop on Windows, Linux and MacOS.
It is a tool for uploading/downloading files and directories to iRODS,
for editing and searching metadata in iRODS.
Finally, being platform independent, 
Hamster-source-code can be used as example code for custom developments to interface your own research-environment with iRODS.

# Functionality
* platform independent GUI (Windows, Linux, MacOS, python, Qt, mostly-one-click-interface MOCI)
* user program (no admin rights needed for running or installation)
* connect with any iRODS (like `iinit`, `ils`, `ipwd`, `icd`)
* metadata: add/edit/delete on dataobjects & collections (like `imeta ls|add|mod|rm` on dataobject & collections)
* metadata: copy/paste/undo on dataobjects & collections
* metadata: search (like `imeta qu` on dataobject & collections)
* upload files and directories (like `iput -r -d -C`).
Optionally: add checksum-before-upload for later comparison with iRODS-checksums
* download files and directories (like `iget -r`)
* rename data objects & collections (like `imv`)
* delete data objects & collections (like `irm -r`)
* inspect object & collection: show all metadata, show replica's (like `ilsresc`)
* view iRODS users & groups (like `igroupadmin lg`)

# Logging in to iRODS
Hamster supports two ways to login to iRODS. 
The first method is to re-use an already setup iRODS environment. 
The other method is via a pure Python SSL session (without a local `irods_environment.json`). 
In this case a settingsfile `[USER_HOME_PATH]/.hamster.json` holds the environment settings and user credentials.

### Method 1: Using irods environment
- [ ] Login to your iRODS environment using `iinit`
- [ ] Run Hamster `python3 main.py`
- [ ] Hamster will use the iRODS environment and piggy-bag on the active iRODS session. 
It will create a settingsfile `[USER_HOME_PATH]/.hamster.json`

### Method 2: Authentication using build-in pure python
- [ ] Create a settingsfile `[USER_HOME_PATH]/.hamster.json`
- [ ] Run Hamster `python3 main.py`

# Installing Hamster
### Virtual environment
First, you may want to setup a virtual environment
```bash
python3 -m venv hamsterenv

on Windows: call hamsterenv\scripts\activate.bat
on Linux:   source hamsterenv/bin/activate

python3 -m pip install --upgrade pip
```

### Clone repository and install libs
```bash
git clone https://github.com/Andries-B/Hamster.git
cd Hamster/src
python3 -m pip install -r requirements.txt
```

# Running Hamster
```bash
python3 main.py
```

# Optional: Creating an installer
```
pyinstaller Hamster.spec
```

# Dependencies
- The software is written in pure Python: Python >= 3.4 is needed
- Python libraries: PyQt6, python-irodsclient >= 1.0.0
- iRODS server: iRODS 4.2.7, 4.2.8, 4.2.9, 4.2.10, 4.3.0 are known to work
- iRODS server: only port 1247 is needed, no additional iRODS plugins are needed
- iRODS server: native or PAM authentication, irods_environment or pure python (no icommands dependency), connection over SSL
- Tested on Linux
- Tested on Windows (working: pure python, SSL, PAM authentication)
- Tested on MacOS
- Expected to work on iOS (not tested)
