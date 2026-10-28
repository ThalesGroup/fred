# Copyright Thales 2026
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Regenerate the synthetic `.msg` fixtures: `python build_msg_fixtures.py`.

No permissively licensed Outlook samples were found, so this writes minimal
[MS-CFB] v3 compound files carrying [MS-OXMSG] properties (stdlib only).
"""

from __future__ import annotations

import struct
from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path

SECTOR, MINI_SECTOR, MINI_CUTOFF = 512, 64, 4096
FREE, END_OF_CHAIN, FAT_SECT, NO_STREAM = 0xFFFFFFFF, 0xFFFFFFFE, 0xFFFFFFFD, 0xFFFFFFFF
PT_INT32, PT_TIME, PT_STRING, PT_BINARY = 0x0003, 0x0040, 0x001F, 0x0102
PropValue = int | datetime | str | bytes


class Node:
    def __init__(self, name: str, data: bytes | None = None, children: list[Node] | None = None):
        self.name, self.data, self.children = name, data, children if children is not None else []
        self.sid, self.left, self.right, self.child, self.start, self.size = 0, NO_STREAM, NO_STREAM, NO_STREAM, END_OF_CHAIN, 0


def _cfb_key(node: Node) -> tuple[int, str]:
    return len(node.name), node.name.upper()


def _balanced(children: list[Node]) -> int:
    """Link siblings as a balanced binary search tree and return the root sid."""
    if not children:
        return NO_STREAM
    mid = len(children) // 2
    root = children[mid]
    root.left, root.right = _balanced(children[:mid]), _balanced(children[mid + 1 :])
    return root.sid


def write_cfb(path: Path, root_children: list[Node]) -> None:
    root = Node("Root Entry", children=root_children)
    nodes: list[Node] = []

    def collect(node: Node) -> None:
        node.sid = len(nodes)
        nodes.append(node)
        node.children.sort(key=_cfb_key)
        for child in node.children:
            collect(child)

    collect(root)
    for node in nodes:
        if node.data is None:
            node.child = _balanced(node.children)

    mini_stream, mini_fat, big = bytearray(), [], []
    for node in nodes:
        if node.data is None:
            continue
        node.size = len(node.data)
        if node.size < MINI_CUTOFF:
            count = max(1, -(-node.size // MINI_SECTOR)) if node.size else 0
            if count:
                node.start = len(mini_fat)
                mini_fat.extend(range(node.start + 1, node.start + count))
                mini_fat.append(END_OF_CHAIN)
                mini_stream += node.data.ljust(count * MINI_SECTOR, b"\0")
        else:
            big.append(node)

    def sectors(data: bytes) -> int:
        return -(-len(data) // SECTOR) if data else 0

    dir_slots = -(-len(nodes) // 4) * 4
    dir_bytes = b"\0" * (dir_slots * 128)  # placeholder: entries are written once start sectors are known
    mini_fat_bytes = struct.pack(f"<{len(mini_fat)}I", *mini_fat) if mini_fat else b""
    mini_fat_bytes = mini_fat_bytes.ljust(sectors(mini_fat_bytes) * SECTOR, b"\xff")
    blobs: list[tuple[str, bytes]] = [("dir", dir_bytes), ("minifat", mini_fat_bytes), ("ministream", bytes(mini_stream))]
    blobs += [(f"node{n.sid}", n.data or b"") for n in big]

    data_sectors = sum(sectors(b) for _, b in blobs)
    fat_count = 1
    while fat_count * (SECTOR // 4) < data_sectors + fat_count:
        fat_count += 1
    fat = [FAT_SECT] * fat_count
    starts: dict[str, int] = {}
    for name, blob in blobs:
        count = sectors(blob)
        if not count:
            starts[name] = END_OF_CHAIN
            continue
        starts[name] = len(fat)
        fat.extend(range(len(fat) + 1, len(fat) + count))
        fat.append(END_OF_CHAIN)
    fat.extend([FREE] * (fat_count * (SECTOR // 4) - len(fat)))

    root.start, root.size = starts["ministream"], len(mini_stream)
    for n in big:
        n.start = starts[f"node{n.sid}"]
    blobs[0] = ("dir", b"".join(_dir_entry(n) for n in nodes) + b"".join(_empty_dir_entry() for _ in range(dir_slots - len(nodes))))

    difat = list(range(fat_count)) + [FREE] * (109 - fat_count)
    header = struct.pack(
        "<8s16sHHHHH6sIIIIIIIII",
        bytes.fromhex("D0CF11E0A1B11AE1"),
        b"\0" * 16,
        0x003E,
        0x0003,
        0xFFFE,
        9,
        6,
        b"\0" * 6,
        0,
        fat_count,
        starts["dir"],
        0,
        MINI_CUTOFF,
        starts["minifat"] if mini_fat else END_OF_CHAIN,
        sectors(mini_fat_bytes),
        END_OF_CHAIN,
        0,
    ) + struct.pack("<109I", *difat)
    body = struct.pack(f"<{len(fat)}I", *fat) + b"".join(b.ljust(sectors(b) * SECTOR, b"\0") for _, b in blobs)
    path.write_bytes(header + body)


def _dir_entry(node: Node) -> bytes:
    name = node.name.encode("utf-16-le") + b"\0\0"
    kind = 5 if node.name == "Root Entry" else (2 if node.data is not None else 1)
    return struct.pack("<64sHBBIII16sIQQIQ", name, len(name), kind, 1, node.left, node.right, node.child, b"\0" * 16, 0, 0, 0, node.start, node.size)


def _empty_dir_entry() -> bytes:
    return struct.pack("<64sHBBIII16sIQQIQ", b"", 0, 0, 0, NO_STREAM, NO_STREAM, NO_STREAM, b"\0" * 16, 0, 0, 0, 0, 0)


def _filetime(value: datetime) -> int:
    return int((value - datetime(1601, 1, 1, tzinfo=timezone.utc)).total_seconds() * 10_000_000)


def properties(props: list[tuple[int, int, PropValue]], header: bytes) -> list[Node]:
    """Build the `__properties_version1.0` stream plus one substream per variable-size value."""
    entries, streams = bytearray(header), []
    for pid, ptype, value in props:
        tag = (pid << 16) | ptype
        if isinstance(value, int):
            entries += struct.pack("<IIi4x", tag, 6, value)
        elif isinstance(value, datetime):
            entries += struct.pack("<IIQ", tag, 6, _filetime(value))
        else:
            raw = value.encode("utf-16-le") if isinstance(value, str) else value
            entries += struct.pack("<IIII", tag, 6, len(raw) + (2 if isinstance(value, str) else 0), 0)
            streams.append(Node(f"__substg1.0_{pid:04X}{ptype:04X}", raw))
    return [Node("__properties_version1.0", bytes(entries)), *streams]


def message(
    props: list[tuple[int, int, PropValue]],
    recipients: Sequence[tuple[str, str, int]] = (),
    attachments: Sequence[tuple[str, bytes | list[Node]]] = (),
    *,
    embedded: bool = False,
) -> list[Node]:
    """A message's nodes; an attachment given as nodes is an embedded message (attach method 5)."""
    storages = []
    for i, (name, address, kind) in enumerate(recipients):
        children = properties([(0x3001, PT_STRING, name), (0x39FE, PT_STRING, address), (0x0C15, PT_INT32, kind)], b"\0" * 8)
        storages.append(Node(f"__recip_version1.0_#{i:08X}", children=children))
    for i, (file_name, data) in enumerate(attachments):
        if isinstance(data, bytes):
            children = properties([(0x3707, PT_STRING, file_name), (0x3705, PT_INT32, 1), (0x3701, PT_BINARY, data)], b"\0" * 8)
        else:
            children = [*properties([(0x3001, PT_STRING, file_name), (0x3705, PT_INT32, 5)], b"\0" * 8), Node("__substg1.0_3701000D", children=data)]
        storages.append(Node(f"__attach_version1.0_#{i:08X}", children=children))
    # [MS-OXMSG] 2.4.1: the top-level header has 8 more reserved bytes than an embedded one.
    header = struct.pack("<8xIIII", len(recipients), len(attachments), len(recipients), len(attachments)) + (b"" if embedded else b"\0" * 8)
    return [*properties(props, header), *storages, *([] if embedded else [Node("__nameid_version1.0", children=[])])]


SENT = datetime(2026, 10, 27, 9, 30, tzinfo=timezone.utc)
COMMON: list[tuple[int, int, PropValue]] = [
    (0x0C1A, PT_STRING, "Jane Doe"),
    (0x5D01, PT_STRING, "jane.doe@example.com"),
    (0x0039, PT_TIME, SENT),
    (0x1035, PT_STRING, "<msg-001@example.com>"),
    (0x1042, PT_STRING, "<msg-000@example.com>"),
]
RECIPIENTS = [("Bob Martin", "bob@example.com", 1), ("Carol White", "carol@example.com", 2), ("Hidden Person", "hidden@example.com", 3)]
HOSTILE_HTML = (
    "<html><head><style>p{color:red}</style><script>alert('x')</script></head>"
    '<body><p onclick="steal()">Quarterly <b>numbers</b> attached.</p>'
    '<img src="https://tracker.example.com/pixel.gif" alt="">'
    '<img src="cid:logo" alt="Company logo">'
    '<a href="javascript:steal()">click</a> <a href="https://example.com/report">report</a></body></html>'
)
SIGNED_MIME = (
    b'Content-Type: multipart/signed; protocol="application/pkcs7-signature"; micalg=sha-256; boundary="sig"\r\n\r\n'
    b'--sig\r\nContent-Type: multipart/mixed; boundary="mix"\r\n\r\n'
    b"--mix\r\nContent-Type: text/plain; charset=utf-8\r\n\r\nSigned body text.\r\n"
    b'--mix\r\nContent-Type: application/pdf\r\nContent-Disposition: attachment; filename="contract.pdf"\r\nContent-Transfer-Encoding: base64\r\n\r\nU0VDUkVULUNPTlRSQUNU\r\n'
    b"--mix--\r\n"
    b'--sig\r\nContent-Type: application/pkcs7-signature; name="smime.p7s"\r\nContent-Disposition: attachment; filename="smime.p7s"\r\n\r\nSIG\r\n'
    b"--sig--\r\n"
)

MINUTES_EML = (
    b"From: Alan Smith <alan@example.com>\r\nTo: team@example.com\r\nBcc: hidden@example.com\r\n"
    b"Date: Mon, 26 Oct 2026 14:00:00 +0000\r\nSubject: Meeting minutes\r\nContent-Type: text/plain; charset=utf-8\r\n\r\n"
    b"Minutes of the weekly meeting.\r\n"
)


def build(directory: Path) -> None:
    write_cfb(
        directory / "plain_with_attachments.msg",
        message(
            [(0x001A, PT_STRING, "IPM.Note"), (0x0037, PT_STRING, "Budget review 2027"), (0x1000, PT_STRING, "Hello team,\r\n\r\nPlease review the budget before Friday.\r\n"), *COMMON],
            RECIPIENTS,
            [("report.pdf", b"%PDF-1.4 SECRET-PDF-CONTENT"), ("photo.png", b"\x89PNG SECRET-IMAGE-CONTENT")],
        ),
    )
    write_cfb(
        directory / "html_only.msg",
        message([(0x001A, PT_STRING, "IPM.Note"), (0x0037, PT_STRING, "HTML only"), (0x1013, PT_BINARY, HOSTILE_HTML.encode("utf-8")), (0x3FDE, PT_INT32, 65001), *COMMON], RECIPIENTS[:1]),
    )
    write_cfb(
        directory / "rtf_only.msg",
        message([(0x001A, PT_STRING, "IPM.Note"), (0x0037, PT_STRING, "RTF only"), (0x1009, PT_BINARY, b"\x00" * 16), *COMMON], RECIPIENTS[:1], [("notes.docx", b"PK SECRET-DOCX")]),
    )
    write_cfb(directory / "signed.msg", message([(0x001A, PT_STRING, "IPM.Note.SMIME.MultipartSigned"), (0x0037, PT_STRING, "Signed contract"), *COMMON], RECIPIENTS[:1], [("smime.p7m", SIGNED_MIME)]))
    embedded_contract = message(
        [(0x001A, PT_STRING, "IPM.Note"), (0x0037, PT_STRING, "Supplier contract draft"), (0x1000, PT_STRING, "Here is the draft contract for review."), *COMMON],
        RECIPIENTS,
        [("contract.pdf", b"%PDF-1.4 SECRET-CONTRACT")],
        embedded=True,
    )
    write_cfb(
        directory / "with_embedded.msg",
        message(
            [(0x001A, PT_STRING, "IPM.Note"), (0x0037, PT_STRING, "Fwd: supplier contract"), (0x1000, PT_STRING, "See the two mails below."), *COMMON],
            RECIPIENTS[:1],
            [("Supplier contract draft", embedded_contract), ("minutes.eml", MINUTES_EML), ("invoice.pdf", b"%PDF-1.4 SECRET-INVOICE")],
        ),
    )
    embedded_encrypted = message([(0x001A, PT_STRING, "IPM.Note.SMIME"), (0x0037, PT_STRING, "Confidential offer"), *COMMON], RECIPIENTS[:1], [("smime.p7m", b"0\x82 ENCRYPTED")], embedded=True)
    write_cfb(
        directory / "with_unreadable_attached.msg",
        message(
            [(0x001A, PT_STRING, "IPM.Note"), (0x0037, PT_STRING, "Two attached mails"), (0x1000, PT_STRING, "The parent stays readable."), *COMMON],
            RECIPIENTS[:1],
            [("Confidential offer", embedded_encrypted), ("broken.msg", b"not an OLE file")],
        ),
    )
    write_cfb(directory / "encrypted.msg", message([(0x001A, PT_STRING, "IPM.Note.SMIME"), (0x0037, PT_STRING, "Confidential"), *COMMON], RECIPIENTS[:1], [("smime.p7m", b"0\x82 ENCRYPTED")]))


if __name__ == "__main__":
    build(Path(__file__).parent)
