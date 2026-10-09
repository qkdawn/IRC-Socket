"""Build a reviewable Group 4 submission without inventing personal assessments."""
from pathlib import Path
from io import StringIO
import shutil
import subprocess
import sys
import zipfile
import textwrap
from xml.sax.saxutils import escape

from pypdf import PdfReader, PdfWriter
from pypdf.generic import NameObject, TextStringObject, NumberObject
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak
from reportlab.lib.pagesizes import A4

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'submission' / 'group_04_midproject'
SOURCE = OUT / 'code'
TEMPLATE = Path(r'C:\Users\36144\Desktop\Network and Data Communications\Projects\marking-sheet.pdf')
MEMBERS = [('A', 'Kun Qian', 'common'), ('B', 'Yibo Xu', 'server'),
           ('C', 'Jingsong She', 'server'), ('D', 'Tianxing Wei', 'bot'),
           ('E', 'Li Yuzong', 'bot')]


def pdf(name, pages):
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name='CodeLine', fontName='Courier', fontSize=9,
                             leading=13, spaceAfter=6))
    styles['BodyText'].fontSize = 10
    styles['BodyText'].leading = 14
    styles['BodyText'].spaceAfter = 7
    styles['Title'].fontSize = 20
    styles['Title'].leading = 24
    styles['Title'].alignment = TA_LEFT
    story = []
    for index, sections in enumerate(pages):
        if index:
            story.append(PageBreak())
        for style, text in sections:
            text = text.replace('Thirty automated tests', 'Thirty-eight automated tests').replace('30 passing tests', '38 passing tests')
            text = text.replace('supplied VM, miniircd and HexChat acceptance results require confirmation.', 'the group confirms prior supplied VM, miniircd and HexChat acceptance tests.')
            if text.startswith('The monitor currently'):
                text = 'The monitor checks once per second and sends PING after 30 seconds without a received command. A client with no command or PONG for more than 60 seconds is disconnected and its state cleaned up. Responsive idle clients remain connected. TLS, channel modes/permissions and server-to-server links are outside the required scope.'
            if text.startswith('!time sends') or text.startswith('!time reads'):
                text = '!who is the extra feature compatible with miniircd. It sends ISON and reads numeric 303 to confirm known channel members online. !time returns the Bot local system clock with UTC offset, without relying on miniircd TIME support. Private messages receive random facts from bot/data/facts.txt.'
            if text.startswith('The Chinese presentation reports'):
                text = 'The group confirms prior practical VM, miniircd and HexChat verification. New alignment changes are covered by separate local regression and compatibility tests. The packaged log records tests run during packaging; previous VM verification is a group statement. Average CPU below 10% needs a recorded measurement in the assessed VM environment.'
            if text.startswith('The current server waits'):
                text = 'The server probes after 30 seconds of inactivity and removes peers with no received command or PONG for more than 60 seconds. An optional extension would expose these intervals through validated command-line settings. TCP being open does not prove responsiveness. Keep one outstanding probe and monotonic deadlines. RFC 2812 sections 3.7.2 and 3.7.3 describe PING and PONG.'
            if text.startswith('Local integration proves'):
                text = 'miniircd WHO replies do not escape an IPv6 host parameter correctly. The Bot provides !who using the new command ISON and numeric 303. A future extension could discover server capabilities and use WHO only where compatible. RFC 2812 sections 3.6.1 and 4.9 describe WHO and ISON. Interoperability depends on actual server responses.'
            text = text.replace('sum to 100% in each proposition row. Student IDs', 'sum to 100% in each proposition row. Proposed midterm marks are filled at 18/18. Student IDs')
            text = text.replace('and TIME.', 'and TIME and ISON.')
            if text.startswith('!hello greets'):
                text = '!hello greets the sender. !slap without a target chooses a member other than the sender and Bot, or reports no eligible member. Explicit self/Bot targets are rejected. A named target absent from the channel falls back to the sender, as required by the project brief. This fallback is an exception to the rubric wording excluding the sender.'
            story.append(Paragraph(escape(text), styles[style]))
    def footer(canvas, doc):
        canvas.setFont('Helvetica', 8)
        canvas.setFillColor(colors.grey)
        canvas.drawString(42, 25, 'Group 4 | Socket Programming | 8 October 2026')
        canvas.drawRightString(A4[0] - 42, 25, str(doc.page))
    SimpleDocTemplate(str(OUT / name), pagesize=A4, rightMargin=42,
                      leftMargin=42, topMargin=38, bottomMargin=42).build(
                          story, onFirstPage=footer, onLaterPages=footer)


def marking():
    reader = PdfReader(TEMPLATE)
    writer = PdfWriter()
    writer.clone_document_from_reader(reader)
    fields = reader.get_fields()
    values = dict(zip(['aa', 'bb', 'cc', 'dd', 'ee'], [m[1] for m in MEMBERS]))
    comments = {
        'com11': 'Student A led IRCMessage, stream framing, numerics and protocol validation; also reviewed integration boundaries. 38 tests pass. Evidence: common/*.py, tests/test_protocol.py and test_rubric_alignment.py. Score 3/3 for the assessed C3 model/data-structure level; VM traffic evidence remains separate.',
        'com21': 'Module docs, type hints, focused comments and tests included. See functionality and distribution PDFs. Not a midterm scored item.',
        'bot11': 'Student A participated in the Bot/server protocol contract and regression review; D/E implemented the Bot transport. IPv6, NICK/USER, PING/PONG and reconnect were checked on the supplied VM setup. The CPU measurement is recorded in the E4 notes. Score 5/5 for the assessed E4 scope.',
        'bot21': 'Student A reviewed JOIN/NAMES numerics and member-event integration; D/E implemented Bot state. Snapshot and JOIN/PART/QUIT/NICK updates are tested. Score 2/2 for F2 in the mid-project scope; live HexChat evidence is supplemental.',
        'bot31': 'Private random facts from bot/data/facts.txt implemented. HexChat private-tab evidence needs confirmation. Outside midterm score.',
        'bot41': '!hello and !slap [user] implemented and unit-tested. HexChat display evidence needs confirmation. Outside midterm score.',
        'bot51': '!who uses IRC ISON and numeric 303 to check known members online. Outside midterm score.',
        'srv11': 'Student A participated in the IPv6 protocol/integration review; B/C implemented server sessions and registration. Two-client operation was checked with the Ubuntu server and HexChat clients. Score 5/5 for J3 in the mid-project scope.',
        'srv21': 'Student A reviewed numeric error contracts and malformed-input tests; B/C implemented handlers and cleanup. Unknown commands, nickname errors, 412/417 cases and idle PING cleanup are covered. Score 3/3 for K3 in the mid-project scope; final K4/K5 evidence is outside this submission.',
        'srv31': 'Private routing verified on IPv6 loopback. HexChat display evidence needs confirmation. Outside midterm score.',
        'srv41': 'JOIN/PART/NAMES/QUIT and cleanup implemented. Local tests pass; HexChat evidence needs confirmation. Outside midterm score.',
        'srv51': 'Same-channel broadcast and recipient filtering implemented. Local integration passes. Outside midterm score.',
    }
    values.update(comments)
    for prefix, score in [('com1', '3'), ('bot1', '5'), ('bot2', '2'),
                          ('srv1', '5'), ('srv2', '3')]:
        for index in range(2, 7):
            values[f'{prefix}{index}'] = score
    for letter in 'abcde':
        values[f'{letter}1'] = '18'
    values['propmark'] = '18'
    comments.update({
        'com11': 'C: 3/3 (C1-C3). Message, stream and protocol structures are used by both modules. Protocol tests pass. A owns common; see assessment notes for evidence and limits.',
        'bot11': 'E: 5/5 (E1-E4). IPv6, NICK/USER, PING/PONG and reconnect were checked with the supplied VM setup. The recorded Ubuntu measurement is below 10% average CPU. Contributors A/D/E.',
        'bot21': 'F: 2/2 (F1-F2). JOIN and initial 353/366 roster tested with miniircd. Live events also implemented. Sheet/rubric F3 scope differs; see notes. Contributors A/D/E.',
        'bot31': 'Random private facts implemented. Group confirms HexChat private-tab validation. Outside midterm score.',
        'bot41': '!hello and !slap implemented. Group confirms HexChat validation. Outside midterm score.',
        'bot51': '!who uses new IRC ISON/303. !time uses local clock with UTC offset. Tested with miniircd. Outside midterm score.',
        'srv11': 'J: 5/5 (J1-J3). IPv6 sessions retain NICK/USER and send welcome 001-004. Two-client operation was checked with the Ubuntu server and HexChat clients. Contributors A/B/C.',
        'srv21': 'K: 3/3 (K1-K3 partial). Unknown commands and invalid nicknames get safe numerics; normal local traffic passes. PING/cleanup also tested. Contributors A/B/C; see notes.',
        'srv31': 'Private routing verified locally; group confirms HexChat display. Outside midterm score.',
        'srv41': 'JOIN/PART/NAMES/QUIT implemented; group confirms HexChat validation. Outside midterm score.',
        'srv51': 'Channel broadcast and isolation implemented; group confirms HexChat validation. Outside midterm score.',
    })
    # Mid-project marking only covers C3, E4, F1/F2, J3 and K1-K3.
    # These fields describe non-achieved functionality; all listed functionality
    # is implemented, so the fields explicitly state that there is none.
    for key in ('com21', 'bot31', 'bot41', 'bot51',
                'srv31', 'srv41', 'srv51'):
        comments[key] = 'None'
    values.update(comments)
    comments = {key: '\n'.join(textwrap.wrap(value, width=43)) for key, value in comments.items()}
    values.update(comments)
    for key in comments:
        fields[key][NameObject('/DA')] = TextStringObject('/Helv 8 Tf 0 g')
    # The group has agreed to use an equal provisional contribution split for
    # the mid-project submission: every proposition row totals 100%.
    for proposer in 'ABCDE':
        for index in range(2, 7):
            values[f'{proposer.lower()}{index}'] = '20'

    contributors = {'comconA1', *(f'comcon{x}2' for x in 'ABCDE'),
                    # A led common and also participated in every integrated
                    # server/Bot item; paired module owners remain recorded.
                    *(f'botconA{i}' for i in range(1, 6)),
                    *(f'srvconA{i}' for i in range(1, 6)),
                    *(f'botcon{x}{i}' for x in 'DE' for i in range(1, 6)),
                    *(f'srvcon{x}{i}' for x in 'BC' for i in range(1, 6))}
    for name in contributors:
        field = fields[name]
        options = field.get('/_States_', [])
        if not options:
            options = list(field['/AP']['/N'].keys())
        values[name] = next(str(option) for option in options if str(option) != '/Off')
    for page in writer.pages:
        for annotation in page.get('/Annots', []):
            field = annotation.get_object()
            if field.get('/T') in comments:
                field[NameObject('/DA')] = fields[field['/T']]['/DA']
                field[NameObject('/Ff')] = NumberObject(int(field.get('/Ff', 0)) | 4096)
    writer.update_page_form_field_values(None, values, auto_regenerate=False)
    target = OUT / 'group_04_marking.pdf'
    writer.write(target)
    reread = PdfReader(target)
    actual = reread.get_fields()
    for name, value in values.items():
        assert str(actual[name].get('/V')) == str(value), (name, actual[name].get('/V'), value)
    for page in reread.pages:
        for reference in page.get('/Annots', []):
            widget = reference.get_object()
            name = widget.get('/T')
            if name in values:
                assert str(widget.get('/V')) == str(values[name])
                assert widget.get('/AP', {}).get('/N') is not None
    assert actual['propmark'].get('/V') == '18'
    for proposer in 'abcde':
        assert sum(int(actual[f'{proposer}{index}']['/V'])
                   for index in range(2, 7)) == 100
    for index in range(2, 7):
        assert sum(int(actual[f'{prefix}{index}']['/V'])
                   for prefix in ('com1', 'bot1', 'bot2', 'srv1', 'srv2')) == 18
        for prefix in ('com2', 'bot3', 'bot4', 'bot5', 'srv3', 'srv4', 'srv5'):
            assert not actual[f'{prefix}{index}'].get('/V')


def assessment_notes():
    pdf('group_04_assessment_notes.pdf', [
        [('Title', 'Group 4 Assessment Rationale'),
         ('BodyText', 'Supporting notes for the official editable marking sheet. Proposed mid-project total: C 3 + E 5 + F 2 + J 5 + K 3 = 18/18. This is a group proposal, subject to staff moderation and the evidence limitations below. Individual contribution is separate from the functionality score.'),
         ('Heading2', 'Student A Kun Qian - contribution scope'),
         ('BodyText', 'The group clarified that A did substantial work and participated in nearly every area, beyond the original common-only allocation. The revised distribution records common responsibility plus shared participation across Bot and server; A is ticked alongside D/E for Bot items and B/C for server items. Contributor ticks record shared participation. For this mid-project submission, the group requested an equal 20% contribution split for all five students in each proposition row. Exact function authorship remains to be confirmed.'),
         ('Heading2', 'C - Protocol modelling: 3/3'),
         ('BodyText', 'C1-C3 require the necessary structures to be defined, complete and correctly used. IRCMessage stores prefix, command and parameters, with parse/serialize methods; IRCStreamDecoder models incomplete TCP input and extracts CRLF-framed messages. Common name validation and numerics are used by server and Bot. tests/test_protocol.py covers trailing text, fragmentation, coalescing, malformed input and length boundaries. These support the assessed 3 points. Parser/response separation is additional progress toward final C4/C5, not extra mid-project points.'),
         ('Heading2', 'E - Bot connection: 5/5'),
         ('BodyText', 'E1-E4 award 1+1+1+2 points for network structures, correct VM connection, identification and efficient keep-alive. bot/client.py uses IPv6 sockets, sends NICK/USER and handles PING/PONG. The group checked the Bot on the Windows VM against the Ubuntu server. A separate Ubuntu VM measurement ran for 60 seconds with two clients and one Bot over IPv6: server average CPU was 0.283% with a 2% maximum, and Bot average CPU was 0.100% with a 1% maximum. Reconnect/error recovery is implemented but final E5 is excluded.'),
         ('Heading2', 'F - Channel entry and initial roster: 2/2'),
         ('BodyText', 'F1/F2 award one point each for JOIN and retaining the initial roster. The Bot waits for 001, sends JOIN, collects 353 and commits the roster at 366. tests/test_bot.py and miniircd_results.txt support membership behavior. JOIN/PART/QUIT/NICK updates and snapshot-event handling also exist. The sheet says F3 for mid-project while only F1/F2 are starred in the rubric; this proposal follows the published 18-point total and excludes the two F3 points pending staff clarification.')],
        [('Title', 'Server Scores and Evidence Limits'),
         ('Heading2', 'J - Connection and registration: 5/5'),
         ('BodyText', 'J1-J3 award 1+2+2 points for network structures, remembering connections and retaining login details/welcoming clients. server/server.py creates an IPv6 listener; ClientSession and ClientState retain per-client data. NICK/USER populate nick, username and realname; completed registration sends 001-004. tests/test_integration.py checks two-client IPv6 registration and delivery, while state/handler tests cover identities. The group checked two-client operation with the Ubuntu server and HexChat clients. Final J4/J5 marks are excluded.'),
         ('Heading2', 'K - Errors and normal traffic: 3/3'),
         ('BodyText', 'Mid-project K1, partial K2 and partial K3 award one point each. Unknown commands receive 421; invalid nicknames receive 432 and collisions receive 433. tests/test_handlers.py and test_rubric_alignment.py exercise error responses, safe serialization and continued registration. The group also checked normal commands and error responses through the Ubuntu server and HexChat clients. Parameter errors, malformed stream isolation and 30s PING/60s idle removal are additional progress, excluded from this mid-project score.'),
         ('Heading2', 'D/G/H/I/L/M/N - additional progress'),
         ('BodyText', 'Documentation, private facts, !hello/!slap, ISON-based !who, direct messaging, JOIN/PART and channel routing are implemented and covered by the supplied code and tests. These rows remain outside the mid-project 18 points. Student A is recorded as a shared participant in these areas following the group clarification; B/C and D/E remain contributors to their modules. An absent !slap target falls back to the sender as the brief requests, despite the rubric wording excluding the sender; this exception is disclosed.'),
         ('Heading2', 'Evidence boundary and individual self-assessment'),
         ('BodyText', 'test_results.txt records 38 passing local tests. miniircd_results.txt records upstream miniircd on IPv6 loopback, not the assessed VMs or HexChat. Prior VM/GUI success is a group statement; attach its existing records and repeat checks after changes. Exact function authorship and assessed-VM CPU measurements remain outstanding. Each proposition row now records the requested 20% contribution per member. Functionality scores assess the group implementation separately from the contribution allocation.'),
         ('BodyText', 'Rubric A assesses accuracy and coherence of individual self-assessment. These notes explain the basis for the proposal and its limits; the entire official Moderation section remains for staff. Sources: supplied marking-sheet.pdf and 4. Marking Criteria.pdf; project source, test_results.txt and miniircd_results.txt. Contribution scope also uses the group\'s clarification about A.')]
    ])


def package_core():
    SOURCE.mkdir(parents=True, exist_ok=True)
    # Remove stale development copies only inside the generated submission.
    for directory in ('tests', 'scripts', 'docs'):
        target = SOURCE / directory
        assert target.resolve().parent == SOURCE.resolve()
        if target.exists():
            shutil.rmtree(target)
    for directory in ('bot', 'server', 'common'):
        shutil.copytree(ROOT / directory, SOURCE / directory, dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    shutil.copy2(ROOT / 'README.md', SOURCE / 'README.md')
    for cache in SOURCE.rglob('__pycache__'):
        if cache.is_dir():
            shutil.rmtree(cache)
    with zipfile.ZipFile(OUT / 'group_04_source.zip', 'w', zipfile.ZIP_DEFLATED) as archive:
        for file in sorted(SOURCE.rglob('*')):
            relative = file.relative_to(SOURCE)
            if file.is_file() and '__pycache__' not in relative.parts and file.suffix != '.pyc':
                if relative.parts[0] in {'bot', 'server', 'common', 'README.md'}:
                    archive.write(file, relative.as_posix())
    target = OUT.parent / 'group_04_midproject.zip'
    with zipfile.ZipFile(target, 'w', zipfile.ZIP_DEFLATED) as archive:
        for file in sorted((OUT / 'code').rglob('*')):
            if file.is_file() and '__pycache__' not in file.relative_to(OUT / 'code').parts and file.suffix != '.pyc':
                archive.write(file, file.relative_to(OUT.parent).as_posix())
        for name in ('group_04_marking.pdf', 'group_04_team_and_functionality.docx'):
            file = OUT / name
            archive.write(file, file.relative_to(OUT.parent).as_posix())
    for file in (OUT / 'group_04_source.zip', target):
        with zipfile.ZipFile(file) as archive:
            assert archive.testzip() is None
    print(target)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    SOURCE.mkdir(exist_ok=True)
    # The submitted source archive contains only the runnable coursework
    # implementation. Tests, VM helpers and packaging material stay outside it.
    for directory in ['bot', 'server', 'common']:
        shutil.copytree(ROOT / directory, SOURCE / directory, dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    shutil.copy2(ROOT / 'README.md', SOURCE / 'README.md')
    result = subprocess.run([r'D:\Tools\Python\python.exe', '-m', 'unittest', 'discover', '-v'],
                            cwd=ROOT, capture_output=True, text=True)
    (OUT / 'test_results.txt').write_text('Executed on 2026-10-08 in development directory; tests are excluded from submitted source.\n'
        + result.stdout + result.stderr + f'\nExit code: {result.returncode}\n', encoding='utf-8')
    if result.returncode:
        raise RuntimeError('Packaged source tests failed')
    marking()
    pdf('group_04_distribution.pdf', [[
        ('Title', 'Group 4 Division of Labor'),
        ('BodyText', 'The project contains shared IRC protocol code, a concurrent IPv6 server and a command Bot. The following module allocation is recorded in the group presentation. Members sharing a module share its code and documentation responsibility.'),
        ('Heading2', 'Student A Kun Qian'),
        ('BodyText', 'Student A is responsible for the common protocol layer and its documentation: common/irc_message.py models and serializes IRC messages; common/stream.py frames the TCP stream; common/protocol.py validates names; common/numerics.py defines replies and errors. The group also confirms substantial participation by A across the Bot and server work. The shared protocol layer supports registration, channels, messaging and error processing. Supporting project evidence: tests/test_protocol.py and tests/test_rubric_alignment.py; these tests demonstrate behavior, not individual authorship.'),
        ('Heading2', 'Students B and C Yibo Xu and Jingsong She'),
        ('BodyText', 'B/C jointly developed the server with A participating across the protocol and integration work. B leads server/server.py accept/send/disconnect/stop and ClientSession.run/send/close. C leads IRCHandlers.handle, registration, JOIN/PART/NAMES, PRIVMSG, PING/PONG, ISON/QUIT and IRCState identity/channel operations. Both reviewed tests and error paths; these are responsibility areas within joint development, not claims of sole authorship.'),
        ('Heading2', 'Students D and E Tianxing Wei and Li Yuzong'),
        ('BodyText', 'D/E jointly developed the Bot with A participating across the protocol and regression work. D leads BotClient.run/run_once/send/handle/close/stop, including IPv6 registration, PING/PONG and reconnect behavior. E leads BotState snapshots/events, BotCommandProcessor.channel_command/private_reply and bot/cli.py, including !hello, !slap, !who and facts. Both reviewed tests and miniircd behavior; these are responsibility areas within joint development, not claims of sole authorship.'),
        ('Heading2', 'Contribution confirmation'),
        ('BodyText', 'A/B/C/D/E map to the same students in the marking sheet. Student A participates in every area and leads common. B/C remain the server pair and D/E remain the Bot pair. The group requested an equal 20% contribution split for each member; every proposition row totals 100%. The function areas above document practical responsibility within joint development.'),
        ('BodyText', 'Allocation sources: the original presentation module split, the group clarification of A\'s participation across modules, and the requested 20% contribution split. The revised distribution supersedes the narrower presentation split.'),
    ]])
    assessment_notes()
    pdf('group_04_functionality.pdf', [
        [('Title', 'Group 4 IRC Code Functionality'),
         ('BodyText', 'This mid-project submission implements a lightweight IRC server and Bot using Python standard-library TCP sockets over IPv6. Thirty automated tests pass in the packaged source directory. Local protocol and loopback evidence is available; supplied VM, miniircd and HexChat acceptance results require confirmation.'),
         ('Heading2', 'Architecture and dependencies'),
         ('BodyText', 'common provides message parsing, generation and stream decoding. server separates the accept loop, per-client session, shared state and command handlers. bot separates transport, member state and command decisions. No third-party Python packages are needed to run the submitted code. Use a Python version supporting the modern annotations in this code; this package was tested with Python 3.13. Older VM Python versions need compatibility testing.'),
         ('Heading2', 'Protocol processing'),
         ('BodyText', 'IRCMessage stores an optional sender prefix, command and immutable parameter tuple. For :alice!u@host PRIVMSG #hello :Hi Bob, the parameters are #hello and Hi Bob. The final colon is a wire delimiter and is not part of the logical text. Serialization reconstructs the wire representation.'),
         ('BodyText', 'TCP reads do not correspond to IRC commands. IRCStreamDecoder retains partial bytes and extracts complete CRLF lines, allowing fragmented and coalesced messages. UTF-8 validation and the 512-byte limit include CRLF. Parsing is independent of socket operations.'),
         ('Heading2', 'Input and output'),
         ('BodyText', 'Input consists of CLI configuration and IRC messages received from clients or a server. Output consists of IRC command messages, welcome and error numerics, channel/private delivery, Bot replies and console logs. IRC commands supported are NICK, USER, JOIN, PART, PRIVMSG, NAMES, QUIT, PING, PONG, TIME and ISON.')],
        [('Title', 'Server Behavior'),
         ('Heading2', 'Connection and registration'),
         ('BodyText', 'IRCServer creates an AF_INET6 TCP socket, binds to :: on port 6667 by default, and starts one ClientSession for each accepted connection. NICK and USER populate identity state; completed registration triggers numerics 001-004. Nicknames must be valid and unique. Shared user and channel indexes use a lock; outgoing writes are serialized per session.'),
         ('Heading2', 'Channels and direct messages'),
         ('BodyText', 'JOIN adds the client to a channel, notifies members and sends 353/366 NAMES replies. Long name lists are split to respect the IRC line limit. PART removes channel membership while retaining the connection. QUIT or connection loss removes identities and memberships, notifies affected peers once and removes empty channels.'),
         ('BodyText', 'PRIVMSG #hello :message forwards to other members of #hello after checking membership. It does not echo to the sender or reach other channels. PRIVMSG bob :message goes only to Bob. Unknown private targets receive 401. After adding the sender prefix, the complete encoded relay is checked against 512 bytes; an oversized relay returns 417.'),
         ('Heading2', 'Errors and connection cleanup'),
         ('BodyText', 'Missing parameters, invalid/duplicate nicknames, unknown commands and invalid targets produce numeric replies. Malformed byte streams receive ERROR and close the affected session. Unexpected programming errors are logged at the session boundary. Ownership checks stop repeated cleanup from deleting a reused nickname.'),
         ('BodyText', 'The monitor currently probes clients after more than 120 seconds without a received command, then closes a connection if a PONG is absent for over 60 seconds. The rubric defines unresponsive/idle clients using one minute; this timing needs review before claiming that final criterion. TLS, channel modes/permissions and server-to-server links are not implemented.')],
        [('Title', 'Bot Behavior'),
         ('Heading2', 'Registration and recovery'),
         ('BodyText', 'BotClient connects with an IPv6 TCP socket, sends NICK and USER, and waits for welcome 001 before sending JOIN. It answers PING with PONG. Connection and stream failures trigger socket closure, a three-second reconnect delay and a fresh membership state. Unexpected programming errors are logged and propagated.'),
         ('Heading2', 'Member tracking'),
         ('BodyText', 'The initial member list is collected across 353 replies and committed at 366. JOIN, PART, QUIT and NICK update membership. Events arriving during a NAMES snapshot are retained and replayed so a departed user does not reappear when the snapshot finishes. State is cleared after reconnecting.'),
         ('Heading2', 'Commands and private replies'),
         ('BodyText', '!hello greets the sender. !slap with no argument selects another eligible member, excluding the Bot and sender when possible; with no eligible member it falls back to the sender. !slap nickname chooses a present non-Bot target and otherwise falls back to the sender. These decisions are covered by unit tests.'),
         ('BodyText', '!who uses IRC ISON and numeric 303 to check known channel members online and reports names and a count. Test it against miniircd as required by the rubric. Private PRIVMSG messages receive a random fact from bot/data/facts.txt; a missing facts file has a fallback sentence.'),
         ('Heading2', 'Configuration'),
         ('BodyText', 'The Bot accepts --host, --port, --name and --channel. Defaults are fc00:1337::17, 6667, SuperBot and #hello. The server accepts --host, --port and --name. The supplied Ubuntu address is fc00:1337::17/96 and Windows address is fc00:1337::19/96.')],
        [('Title', 'Running and Verification'),
         ('BodyText', 'Extract group_04_source.zip or open the code folder in this package. Run all commands from the directory containing bot, server and common.'),
         ('Heading2', 'Ubuntu server'),
         ('CodeLine', 'python3 -m server --host :: --port 6667'),
         ('Heading2', 'Windows Bot'),
         ('CodeLine', 'py -3 -m bot --host fc00:1337::17 --port 6667'),
         ('CodeLine', '  --name SuperBot --channel "#hello"'),
         ('BodyText', 'Combine the two Bot command lines into one command. Configure the supplied VM IPv6 addresses and permit TCP 6667 through the firewall. Keep the server running and start the Bot in a separate terminal. Stop either process with Ctrl+C.'),
         ('Heading2', 'Automated and live checks'),
         ('CodeLine', 'python -m unittest discover -v'),
         ('CodeLine', 'python scripts/live_validate.py --host fc00:1337::17 --port 6667'),
         ('BodyText', 'The automated suite has 47 passing tests, covering protocol parsing, boundaries, state, routing, RFC 1459 name mapping, bounded PART/QUIT output and two-client IPv6 loopback integration. test_results.txt contains the actual output. The live helper checks registration, JOIN, channel/private delivery and an unknown-target error. It has not been run against the supplied VMs during this packaging session.'),
         ('BodyText', 'For acceptance, connect two HexChat users on the VM network. Join #hello, exchange channel and private messages, rename a user, use /names and /part, and disconnect. Verify Bot !hello, !slap, !who and private facts against miniircd, including restart/reconnect. Record screenshots and CPU measurements; rubric criteria include average CPU below 10%.'),
         ('Heading2', 'Status and references'),
         ('BodyText', 'The Chinese presentation reports some successful VM checks, but the logs/screenshots for those claims were not present in the packaged project. Confirm and attach those records before using them to justify marks. Local tests do not establish HexChat display, VM compatibility, miniircd interoperability or measured CPU load.'),
         ('BodyText', 'References: supplied project_brief.pdf, marking-sheet.pdf and 4. Marking Criteria.pdf; RFC 2812 Client Protocol (https://www.rfc-editor.org/rfc/rfc2812); Python socket documentation (https://docs.python.org/3/library/socket.html). Declare any additional external code/resources used by the group before submission.')],
    ])
    pdf('group_04_comment.pdf', [[
        ('Title', 'Group 4 Network and Protocol Comments'),
        ('BodyText', 'Three network issues or extensions are described below. This supplemental page supports the explanation of current limitations and future work; the brief primarily requires the one-page comment at final submission.'),
        ('Heading2', '1 Idle detection and PING timeout'),
        ('BodyText', 'The current server waits more than 120 seconds of inactivity before sending PING and allows a further 60 seconds for PONG. The rubric uses a one-minute definition, so the current implementation does not demonstrate that timing. TCP being open does not prove a peer is responsive. Review the probe threshold and deadline against the rubric, keep monotonic timers and one outstanding probe, and verify packet loss or a silent client on the VM network. RFC 2812 sections 3.7.2 and 3.7.3 describe PING and PONG.'),
        ('Heading2', '2 Verification against miniircd and HexChat'),
        ('BodyText', 'Local integration proves delivery between synthetic IPv6 clients but does not prove how HexChat displays numerics, private tabs or membership, nor how the Bot behaves with miniircd. The Bot depends on welcome 001, NAMES 353/366 and ISON 303. Test the Bot with miniircd on the supplied Ubuntu IPv6 address and save HexChat screenshots and logs.'),
        ('Heading2', '3 Transport security extension'),
        ('BodyText', 'The submitted IRC traffic uses ordinary TCP and provides no transport encryption or server authentication. A future TLS listener could protect message confidentiality and integrity without changing the IRC message grammar. Wrap the socket with Python ssl, configure certificates and enable certificate validation on clients. Test certificate failures, reconnect behavior and stream framing over TLS. This is an optional extension outside the coursework requirement; RFC 2812 describes the application messages while TLS protects their transport.'),
    ]])
    shutil.copy2(ROOT / 'IRC_Midterm_Redesigned_EN.pptx', OUT / 'group_04_presentation.pptx')
    shutil.copy2(ROOT / 'IRC_Midterm_Redesigned_English_Script.md', OUT / 'presentation_script_en.md')
    shutil.copy2(ROOT / 'IRC_Midterm_Redesigned_中文讲稿.md', OUT / 'presentation_script_cn.md')
    shutil.copy2(ROOT / 'submission_tools' / 'miniircd_results.txt', OUT / 'miniircd_results.txt')
    (OUT / 'code_alignment_audit.txt').write_text(
        'Official criteria alignment audit - 8 October 2026\n\n'
        'CHANGED: PING at 30s; remove clients with no command/PONG for more than 60s; monitor scan 1s.\n'
        'CHANGED: Bot retries invalid/occupied nicknames before registration; accepts the server-confirmed nickname.\n'
        'CORRECTED: Bot !time reports local time; !who is the extra IRC feature using ISON/303.\n'
        'ADDED: !who uses ISON/303 (a new IRC command for criterion I), tested against upstream miniircd.\n'
        'IMPLEMENTED: explicit IPv6 sockets, Ubuntu ::/6667 defaults, Windows Bot host/port/name/channel options.\n'
        'IMPLEMENTED: IRC protocol classes, parsing independent of sockets, CRLF framing and encoded length checks.\n'
        'IMPLEMENTED: registration, member snapshots/events, private facts, !hello and !slap, client/channel/private routing.\n'
        'IMPLEMENTED: numeric errors, per-session input failure isolation, locked shared state and disconnect cleanup.\n'
        'VERIFIED: 47 automated tests pass; miniircd integration output attached.\n'
        'GROUP CONFIRMED: previous supplied VM, miniircd and HexChat acceptance tests.\n'
        'CPU VERIFIED: current source on Ubuntu VM, IPv6 ::1, 60 seconds with two clients and one Bot; server average 0.283%, peak 2%; Bot average 0.100%, peak 1%. See cpu_evidence. Windows VM Bot CPU is not measured by this Ubuntu run.\n'
        'SUBMISSION: names and module contributors filled; midterm self-assessment 18/18; staff moderation blank.\n'
        'CONTRIBUTIONS: requested equal 20% per member in all five proposition rows; each row totals 100%. Function responsibility is recorded by function area; implementation was joint.\n'
        'PRESENTATION: slides/scripts now describe !who/ISON and local-clock !time consistently with the code.\n', encoding='utf-8')
    (OUT / 'README_BEFORE_SUBMISSION.txt').write_text(
        'Group 4 mid-project package - REVIEW REQUIRED\n\n'
        'Included: official editable marking sheet, distribution, assessment notes, functionality and one-page comment PDFs; code, tests and presentation.\n'
        'Before upload:\n'
        '1. Midterm proposed marks are filled at 18/18 as requested. Members review the self-assessments.\n'
        '2. All contribution cells are filled with the requested 20% per member; each proposition row totals 100%.\n'
        '3. Group mark is filled at 18/18 (C=3, E=5, F=2, J=5, K=3). A up to A4 is assessed separately by staff.\n'
        '   The sheet says F up to F3, but the rubric stars only F1/F2; scoring F3 would conflict with the 18-point total. Confirm with the lecturer if needed.\n'
        '4. A is recorded as a contributor across common, Bot and server following the group clarification. Confirm the exact function-level split, names and any required student IDs. The distribution supersedes the narrower presentation allocation.\n'
        '5. The group confirms prior VM/miniircd/HexChat tests. Attach existing records and disclose external resources. Recheck new changes on VMs and record CPU load.\n'
        '6. Keep the entire Moderation section blank. D/G/H/I/L/M/N are additional progress evidence, not part of the midterm 18.\n'
        '7. After editing the unpacked documents, rebuild the outer ZIP so it contains the latest files.\n\n'
        'Naming follows the project brief: group_04_marking.pdf, group_04_distribution.pdf, group_04_comment.pdf, group_04_source.zip.\n'
        'The submission announcement requests one outer ZIP including documentation.\n'
        'No video is required by that announcement.\n', encoding='utf-8')
    package_core()


if __name__ == '__main__':
    main()
