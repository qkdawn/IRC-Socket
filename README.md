# Coursework IRC Socket Project

This repository contains a small IRC server and command bot implemented with Python 3's standard library.

## Quick start

Run the server on Ubuntu:

```bash
python3 -m server --host :: --port 6667
```

Run the bot on the Windows VM:

```powershell
py -3 -m bot --host fc00:1337::17 --port 6667 --name SuperBot --channel '#hello'
```

Run automated tests from the project root:

```bash
python -m unittest discover -v
```

The source archive must retain the top-level `bot`, `server`, and `common` directories.

