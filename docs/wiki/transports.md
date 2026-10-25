# Transports: how bytes and messages reach devices

**Package:** `mastif.resources.transports`. **ADRs:** 0013 (configs), 0014 (streams),
0015 (line I/O), 0016 (SCPI), 0017 (datagrams), 0018 (injection), 0032 (Telnet),
0033 (SSH), 0035 (native vendor libraries).

## Why it exists

Drivers need to talk to devices over TCP, serial, VISA, UDP, Telnet or SSH, or through
a vendor's native library. Each medium has its own
library, its own errors, and its own ways of losing or merging data. If every driver
handled this itself, there would be dozens of slightly different, slightly wrong
implementations. The transports layer handles it once:

- **Framing:** partial reads and back-to-back replies are handled correctly.
- **Timeouts that raise:** a silent device never hangs a run.
- **Typed errors:** `TransportError`, `TransportTimeout`, `ProtocolError`.
- **I/O tracing** through the station's logger.
- **Injection:** drivers never construct connections.

## The stack

```mermaid
flowchart BT
    tcp[TcpTransport] --> bs[BufferedStream]
    ser[SerialTransport] --> bs
    tel[TelnetTransport] --> bs
    sst[SshStreamTransport] --> bs
    sst --> sess[SshSession]
    bs -.implements.-> ST((StreamTransport))
    ST --> sl[StreamLineIO]
    visa[VisaLineIO] -.implements.-> LIO((LineIO))
    sl -.implements.-> LIO
    LIO --> scpi[Scpi]
    dg[DatagramChannel]
    nl[NativeLibrary]
```

| You need to… | Ask for | Built from `kind` |
|---|---|---|
| speak a binary protocol | `io: StreamTransport` | tcp, serial, telnet, ssh |
| speak a text-line protocol | `io: LineIO` | tcp, serial, visa, telnet, ssh |
| drive a SCPI instrument | `io: Scpi` | tcp, serial, visa, telnet, ssh |
| exchange UDP messages | `io: DatagramChannel` | udp |
| run commands on a host | `session: SshSession` | ssh |
| call a vendor DLL | `lib: NativeLibrary` | native |

## Configs: where a device is

Configs live in the station profile under the driver's `config.transport`, and `kind`
picks the model:

```yaml
transport: {kind: tcp, host: 10.0.0.5, port: 5025, timeout: 2.0}
transport: {kind: serial, port: COM3, baudrate: 115200, read_termination: "\r\n"}
transport: {kind: visa, resource: "USB0::0x1234::0x5678::A123::INSTR"}
transport: {kind: udp, host: 192.168.1.50, port: 9000, local_port: 9001}
transport: {kind: telnet, host: 10.0.0.9, login_prompt: "login: ", username: admin,
            password: "...", ready_prompt: "> "}
transport: {kind: ssh, host: 192.168.1.60, username: root, key_file: ~/.ssh/id_ed25519}
transport: {kind: native, library: acmedio, search_paths: ["C:/Program Files/Acme/bin"]}
```

Unknown keys, bad ports and impossible stop bits are rejected before anything opens.
Passwords are secrets (`SecretStr`): they never show in logs or error messages.
Serial, VISA and SSH need extras: `pip install 'mastif[serial]'`, `'mastif[visa]'` or
`'mastif[ssh]'`. Telnet needs nothing extra.

## Behaviours worth knowing

**Streams** (ADR-0014):

- `read_until` keeps any bytes after the terminator for the next read.
- Timeouts cover the whole read.
- `write("text")` encodes, but **never adds a terminator**, because binary protocols
  would break. `LineIO.write_line` adds it.

**SCPI** (ADR-0016):

- `query_float` rejects the instrument's overflow marker `9.9E37`, so an over-range
  reading becomes an error, never a huge "valid" number.
- `identify()` parses `*IDN?`.
- `errors()` drains `SYST:ERR?`.
- `Scpi(io, check_errors=True)` checks for errors after every write.

**Datagrams** (ADR-0017):

- A background thread reads everything.
- `request(msg, match=...)` registers a waiter **before** sending, and returns the first
  datagram the matcher accepts.
- Unsolicited messages go to subscribers, and never get mistaken for replies.
- Retries resend on timeout.
- A failing subscriber is logged and doesn't break the channel.

**Telnet** (ADR-0032):

- Option negotiation (`IAC` sequences) is removed from the data and every option is
  refused, so drivers see clean bytes, even when the server negotiates mid-reply.
- Lines default to `\r\n`, the Telnet standard.
- The optional login runs during `open`; `ready_prompt` skips the banner that follows.
  A wrong prompt fails `open` with `TransportTimeout` naming the prompt.

**SSH** (ADR-0033):

- `SshSession.run(cmd)` uses one SSH exec channel per command and returns
  `ShellResult(command, output, exit_code, stderr)`: real exit codes, stderr kept
  separate. Each command runs in a fresh shell, so `cd` doesn't carry over.
- The stream (`StreamTransport`, `LineIO`, `Scpi`) is an interactive shell, for targets
  that only offer a CLI.
- Host keys are always checked. `known_hosts: strict` (default) refuses unknown hosts;
  `accept_new` trusts and remembers them. A changed key is always refused.
- Without `password` or `key_file`, the SSH agent and `~/.ssh/id_*` are tried.

**Native libraries** (ADR-0035):

- Declare each function's prototype with `lib.function(name, restype, argtypes)`
  before calling it with `lib.call(name, *args)`; undeclared calls are refused.
- Calls run on one dedicated thread by default (`thread_confined`).
- `StatusCheck` turns status codes into `ProtocolError` with the vendor's text.
- Load failures explain themselves: a missing dependency (add `search_paths`), or a
  32-bit DLL that a 64-bit Python can't load.
- How-to: [Wrap a vendor DLL](guides/wrap-a-vendor-dll.md).

**VISA** (ADR-0015): errors whose text mentions "timeout" become `TransportTimeout`. The
per-read timeout argument is ignored; the resource timeout applies.

## Data flow of one SCPI query

```mermaid
sequenceDiagram
    participant D as Driver
    participant S as Scpi
    participant L as StreamLineIO
    participant T as TcpTransport
    D->>S: query_quantity("MEAS:CURR?", "A")
    S->>L: query("MEAS:CURR?")
    L->>T: write(b"MEAS:CURR?\n")
    L->>T: read_until(b"\n")
    T-->>L: b"+1.8000E-01"
    L-->>S: "+1.8000E-01"
    S-->>D: Quantity(0.18, "A")
```

## Where to look

| What | Where |
|---|---|
| Code | `packages/mastif/src/mastif/resources/transports/` |
| Fakes for tests | [Testing kit](testing-kit.md) |
| API | [reference](../reference/resources.md) |
