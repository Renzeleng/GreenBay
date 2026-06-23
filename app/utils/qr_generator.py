"""
Pure-Python QR code generator that produces SVG output.
Implements QR Code Model 2, versions 1-10, error correction level M.
No external dependencies required.
"""

import re

# ---------------------------------------------------------------------------
# Reed-Solomon GF(256) arithmetic
# ---------------------------------------------------------------------------

GF_EXP = [0] * 512
GF_LOG = [0] * 256

def _init_gf():
    x = 1
    for i in range(255):
        GF_EXP[i] = x
        GF_LOG[x] = i
        x = x << 1
        if x & 0x100:
            x ^= 0x11D
    for i in range(255, 512):
        GF_EXP[i] = GF_EXP[i - 255]

_init_gf()

def _gf_mul(x, y):
    if x == 0 or y == 0:
        return 0
    return GF_EXP[(GF_LOG[x] + GF_LOG[y]) % 255]

def _gf_pow(x, power):
    return GF_EXP[(GF_LOG[x] * power) % 255]

def _gf_poly_mul(p, q):
    r = [0] * (len(p) + len(q) - 1)
    for j, qj in enumerate(q):
        for i, pi in enumerate(p):
            r[i + j] ^= _gf_mul(pi, qj)
    return r

def _rs_generator_poly(nsym):
    g = [1]
    for i in range(nsym):
        g = _gf_poly_mul(g, [1, _gf_pow(2, i)])
    return g

def _rs_encode(msg, nsym):
    gen = _rs_generator_poly(nsym)
    msg_out = list(msg) + [0] * nsym
    for i in range(len(msg)):
        coef = msg_out[i]
        if coef != 0:
            for j in range(1, len(gen)):
                msg_out[i + j] ^= _gf_mul(gen[j], coef)
    return msg_out[len(msg):]

# ---------------------------------------------------------------------------
# QR encoding tables
# ---------------------------------------------------------------------------

# ISO/IEC 18004 Table 9 — EC Level M, versions 1-10.
# (total_codewords, ec_codewords_per_block, [(num_blocks, data_codewords_per_block), ...])
# These are the standard published values; previous approximations here caused
# corrupted/unscannable output for versions 3 and up.
_VERSION_DATA = {
    1:  (26,  10, [(1, 16)]),
    2:  (44,  16, [(1, 28)]),
    3:  (70,  26, [(1, 44)]),
    4:  (100, 18, [(2, 32)]),
    5:  (134, 24, [(2, 43)]),
    6:  (172, 16, [(4, 27)]),
    7:  (196, 18, [(4, 31)]),
    8:  (242, 22, [(2, 38), (2, 39)]),
    9:  (292, 22, [(3, 36), (2, 37)]),
    10: (346, 26, [(4, 43), (1, 44)]),
}

# Alignment pattern positions
_ALIGN_POS = {
    1: [], 2: [6, 18], 3: [6, 22], 4: [6, 26], 5: [6, 30],
    6: [6, 34], 7: [6, 22, 38], 8: [6, 24, 42], 9: [6, 26, 46], 10: [6, 28, 50]
}

# Format info strings for EC level M, masks 0-7
_FORMAT_STRINGS = {
    0: 0b101010000010010,
    1: 0b101000100100101,
    2: 0b101111001111100,
    3: 0b101101101001011,
    4: 0b100010111111001,
    5: 0b100000011001110,
    6: 0b100111110010111,
    7: 0b100101010100000,
}

# Version information strings (18 bits: 6-bit version number + 12-bit BCH ECC),
# required for versions 7 and above. ISO 18004 Annex D. Without this block,
# decoders cannot reliably determine the symbol version, and many will
# refuse to decode the symbol at all — versions 7-10 were unscannable
# until this table and its placement were added.
_VERSION_INFO_STRINGS = {
    7:  0b000111110010010100,
    8:  0b001000010110111100,
    9:  0b001001101010011001,
    10: 0b001010010011010011,
}

def _char_count_bits(version, mode):
    # mode: 'byte' only for our purposes
    if version <= 9:
        return 8
    return 16

def _encode_byte_mode(data: bytes, version: int):
    """Returns list of bits."""
    bits = []
    # Mode indicator: byte = 0100
    bits += [0, 1, 0, 0]
    # Character count
    char_bits = _char_count_bits(version, 'byte')
    n = len(data)
    for i in range(char_bits - 1, -1, -1):
        bits.append((n >> i) & 1)
    # Data
    for byte in data:
        for i in range(7, -1, -1):
            bits.append((byte >> i) & 1)
    return bits

def _bits_to_codewords(bits, total_codewords):
    # Terminator
    for _ in range(min(4, total_codewords * 8 - len(bits))):
        bits.append(0)
    # Pad to byte boundary
    while len(bits) % 8:
        bits.append(0)
    # Pad codewords
    pads = [0b11101100, 0b00010001]
    i = 0
    while len(bits) < total_codewords * 8:
        for b in range(7, -1, -1):
            bits.append((pads[i % 2] >> b) & 1)
        i += 1
    # Convert to bytes
    codewords = []
    for i in range(0, total_codewords * 8, 8):
        cw = 0
        for j in range(8):
            cw = (cw << 1) | bits[i + j]
        codewords.append(cw)
    return codewords

# ---------------------------------------------------------------------------
# QR matrix construction
# ---------------------------------------------------------------------------

def _make_matrix(version):
    size = version * 4 + 17
    return [[None] * size for _ in range(size)]

def _place_finder(matrix, r, c):
    for dr in range(-1, 8):
        for dc in range(-1, 8):
            if 0 <= r + dr < len(matrix) and 0 <= c + dc < len(matrix):
                if dr in (-1, 7) or dc in (-1, 7):
                    matrix[r + dr][c + dc] = 0
                elif (dr, dc) in [(1, 1), (1, 2), (1, 3), (1, 4), (1, 5),
                                   (2, 1), (2, 5), (3, 1), (3, 5),
                                   (4, 1), (4, 5), (5, 1), (5, 2),
                                   (5, 3), (5, 4), (5, 5)]:
                    matrix[r + dr][c + dc] = 0
                else:
                    matrix[r + dr][c + dc] = 1

def _place_timing(matrix, version):
    """
    Timing patterns run along row 6 and column 6 between the finder
    patterns. Skips any cell already set (e.g. by an alignment pattern
    whose center lies on row/col 6) so placement order doesn't matter.
    """
    size = version * 4 + 17
    for i in range(8, size - 8):
        val = 1 if i % 2 == 0 else 0
        if matrix[6][i] is None:
            matrix[6][i] = val
        if matrix[i][6] is None:
            matrix[i][6] = val

def _place_alignment(matrix, version):
    """
    Alignment pattern is a 5x5 module block: dark outer ring, light
    middle ring, single dark center module — like a miniature finder
    pattern. (A previous version inverted the outer ring to light,
    corrupting every QR code at version >= 2.)

    Only positions whose center coincides with one of the three finder
    patterns' own corners are skipped. A previous version skipped any
    position that was merely "already occupied", which incorrectly
    excluded valid alignment patterns that sit on the timing track
    (e.g. (6,22) and (22,6) for version 7) — those overlap the timing
    pattern, not a finder pattern, and the alignment pattern is meant to
    override that segment of the timing track, not be skipped.
    """
    size = version * 4 + 17
    finder_corners = {(6, 6), (6, size - 7), (size - 7, 6)}
    positions = _ALIGN_POS.get(version, [])
    for r in positions:
        for c in positions:
            if (r, c) in finder_corners:
                continue
            for dr in range(-2, 3):
                for dc in range(-2, 3):
                    if abs(dr) == 2 or abs(dc) == 2:
                        matrix[r + dr][c + dc] = 1
                    elif dr == 0 and dc == 0:
                        matrix[r + dr][c + dc] = 1
                    else:
                        matrix[r + dr][c + dc] = 0
            matrix[r][c] = 1

def _reserve_format(matrix, version):
    size = version * 4 + 17
    for i in range(9):
        for pos in [(8, i), (i, 8)]:
            if matrix[pos[0]][pos[1]] is None:
                matrix[pos[0]][pos[1]] = 'F'
    for i in range(size - 8, size):
        if matrix[8][i] is None:
            matrix[8][i] = 'F'
        if matrix[i][8] is None:
            matrix[i][8] = 'F'
    matrix[size - 8][8] = 1  # dark module


def _place_version_info(matrix, version):
    """
    Write the 18-bit version information block, required for versions 7
    and above (ISO 18004 Annex D / Figure 25). Two copies are placed:

      - Top-right block: 6 rows (0-5) x 3 columns (size-11 .. size-9),
        immediately to the LEFT of the top-right finder pattern.
      - Bottom-left block: 3 rows (size-11 .. size-9) x 6 columns (0-5),
        immediately ABOVE the bottom-left finder pattern.

    (A previous version of this function had the row/column roles
    swapped for the top-right block, which overlapped and corrupted the
    finder pattern itself — making every version 7+ QR code unscannable
    even though the rest of the symbol was otherwise correctly built.)
    """
    if version < 7:
        return
    size = version * 4 + 17
    bits = _VERSION_INFO_STRINGS[version]
    for i in range(18):
        bit = (bits >> i) & 1
        # Per spec, bit i sits at (row = i % 3, col = i // 3) within each
        # 3x6 block before accounting for orientation.
        minor = i % 3   # 0..2
        major = i // 3  # 0..5
        # Top-right block: varies by row (major, 0-5), fixed column offset (minor, 0-2)
        matrix[major][size - 11 + minor] = bit
        # Bottom-left block: varies by column (major, 0-5), fixed row offset (minor, 0-2)
        matrix[size - 11 + minor][major] = bit

def _place_data(matrix, data_bits, version):
    """
    Zigzag-place data bits into every still-empty (None) cell, which at
    this point is exactly the data/EC area (all function patterns have
    already been written as 0/1/'F'). Returns a same-shaped boolean grid
    marking which cells are data area, so the masking step can target
    only those cells.
    """
    size = version * 4 + 17
    data_area = [[matrix[r][c] is None for c in range(size)] for r in range(size)]
    bit_idx = 0
    # Columns right to left, skipping column 6 (timing)
    col = size - 1
    going_up = True
    while col >= 0:
        if col == 6:
            col -= 1
            continue
        col_range = [col, col - 1]
        row_range = range(size - 1, -1, -1) if going_up else range(size)
        for row in row_range:
            for c in col_range:
                if c < 0:
                    continue
                if matrix[row][c] is None:
                    if bit_idx < len(data_bits):
                        matrix[row][c] = data_bits[bit_idx]
                        bit_idx += 1
                    else:
                        matrix[row][c] = 0
        going_up = not going_up
        col -= 2

    return data_area

def _apply_mask(matrix, mask_num, version, data_area):
    """
    Apply the given mask pattern — but ONLY to data/error-correction
    modules, never to function patterns (finder, timing, alignment,
    format info, dark module). Masking function patterns destroys the
    very structures a scanner uses to locate and orient the code, which
    is what made every previously-generated QR code unscannable.

    `data_area` is a same-shaped boolean grid: True where the module
    belongs to the data area (computed once, right before data bits are
    placed, since at that point everything still None is data area).
    """
    size = version * 4 + 17
    m = [row[:] for row in matrix]
    for r in range(size):
        for c in range(size):
            if not data_area[r][c]:
                continue
            if isinstance(m[r][c], int):
                apply = False
                if mask_num == 0:
                    apply = (r + c) % 2 == 0
                elif mask_num == 1:
                    apply = r % 2 == 0
                elif mask_num == 2:
                    apply = c % 3 == 0
                elif mask_num == 3:
                    apply = (r + c) % 3 == 0
                elif mask_num == 4:
                    apply = (r // 2 + c // 3) % 2 == 0
                elif mask_num == 5:
                    apply = (r * c) % 2 + (r * c) % 3 == 0
                elif mask_num == 6:
                    apply = ((r * c) % 2 + (r * c) % 3) % 2 == 0
                elif mask_num == 7:
                    apply = ((r + c) % 2 + (r * c) % 3) % 2 == 0
                if apply:
                    m[r][c] ^= 1
    return m

def _write_format(matrix, mask_num, version):
    size = version * 4 + 17
    fmt = _FORMAT_STRINGS[mask_num]
    bits = [(fmt >> (14 - i)) & 1 for i in range(15)]
    # Around top-left finder
    positions_tl = [(8, 0), (8, 1), (8, 2), (8, 3), (8, 4), (8, 5), (8, 7), (8, 8),
                    (7, 8), (5, 8), (4, 8), (3, 8), (2, 8), (1, 8), (0, 8)]
    for i, (r, c) in enumerate(positions_tl):
        matrix[r][c] = bits[i]
    # Bottom-left and top-right
    for i in range(7):
        matrix[size - 1 - i][8] = bits[i]
    matrix[size - 8][8] = 1  # dark module
    for i in range(8):
        matrix[8][size - 8 + i] = bits[7 + i]

def _score_matrix(matrix):
    """Full QR mask-evaluation penalty (ISO 18004 Annex 8.8.2), all 4 rules."""
    size = len(matrix)
    score = 0

    # Rule 1: 5+ consecutive same-color modules in a row or column
    for row in matrix:
        run = 1
        for i in range(1, size):
            if row[i] == row[i - 1]:
                run += 1
            else:
                if run >= 5:
                    score += 3 + (run - 5)
                run = 1
        if run >= 5:
            score += 3 + (run - 5)
    for c in range(size):
        run = 1
        for r in range(1, size):
            if matrix[r][c] == matrix[r - 1][c]:
                run += 1
            else:
                if run >= 5:
                    score += 3 + (run - 5)
                run = 1
        if run >= 5:
            score += 3 + (run - 5)

    # Rule 2: 2x2 blocks of the same color
    for r in range(size - 1):
        for c in range(size - 1):
            v = matrix[r][c]
            if (v == matrix[r][c + 1] == matrix[r + 1][c] == matrix[r + 1][c + 1]):
                score += 3

    # Rule 3: patterns resembling the finder pattern (1011101 with 4-module
    # light border on either side) found in a row or column
    pattern_a = [1, 0, 1, 1, 1, 0, 1, 0, 0, 0, 0]
    pattern_b = [0, 0, 0, 0, 1, 0, 1, 1, 1, 0, 1]
    for row in matrix:
        for i in range(size - 10):
            window = row[i:i + 11]
            if window == pattern_a or window == pattern_b:
                score += 40
    for c in range(size):
        col = [matrix[r][c] for r in range(size)]
        for i in range(size - 10):
            window = col[i:i + 11]
            if window == pattern_a or window == pattern_b:
                score += 40

    # Rule 4: overall dark/light balance away from 50%
    dark = sum(1 for row in matrix for v in row if v == 1)
    total = size * size
    percent_dark = (dark * 100) // total
    prev = (percent_dark // 5) * 5
    nxt = prev + 5
    score += min(abs(prev - 50), abs(nxt - 50)) // 5 * 10

    return score

# ---------------------------------------------------------------------------
# Determine version automatically
# ---------------------------------------------------------------------------

def _get_version(data: bytes) -> int:
    # Data capacity for EC level M (byte mode)
    capacities = {1: 14, 2: 26, 3: 42, 4: 62, 5: 84,
                  6: 106, 7: 122, 8: 152, 9: 180, 10: 213}
    for v in range(1, 11):
        if len(data) <= capacities[v]:
            return v
    raise ValueError(f"Data too long ({len(data)} bytes) for supported versions 1-10")

# ---------------------------------------------------------------------------
# Main encode function
# ---------------------------------------------------------------------------

def generate_qr_svg(text: str, module_size: int = 6, quiet_zone: int = 4) -> str:
    """
    Generate a QR code SVG string for the given text.
    Returns an SVG string.
    """
    data = text.encode('utf-8')
    version = _get_version(data)
    size = version * 4 + 17

    # Get capacity info: total codewords, EC codewords per block, and the
    # list of (num_blocks, data_codewords_per_block) groups. Some versions
    # (8, 9, 10) have two groups with different per-block data sizes.
    total_cw, ec_cw_per_block, groups = _VERSION_DATA[version]
    data_cw = sum(n * dc for n, dc in groups)

    # Encode data bits
    bits = _encode_byte_mode(data, version)
    codewords = _bits_to_codewords(list(bits), data_cw)

    # Split into blocks per group and add Reed-Solomon error correction
    all_data = []
    all_ec = []
    pos = 0
    for num_blocks, block_data_cw in groups:
        for _ in range(num_blocks):
            block = codewords[pos:pos + block_data_cw]
            pos += block_data_cw
            ec = _rs_encode(block, ec_cw_per_block)
            all_data.append(block)
            all_ec.append(ec)

    # Interleave
    final_cw = []
    for i in range(max(len(b) for b in all_data)):
        for b in all_data:
            if i < len(b):
                final_cw.append(b[i])
    for i in range(ec_cw_per_block):
        for b in all_ec:
            final_cw.append(b[i])

    # Convert to bits
    final_bits = []
    for cw in final_cw:
        for i in range(7, -1, -1):
            final_bits.append((cw >> i) & 1)

    # Build matrix
    matrix = _make_matrix(version)
    _place_finder(matrix, 0, 0)
    _place_finder(matrix, 0, size - 7)
    _place_finder(matrix, size - 7, 0)
    if version >= 2:
        _place_alignment(matrix, version)
    _place_timing(matrix, version)
    _reserve_format(matrix, version)
    _place_version_info(matrix, version)
    data_area = _place_data(matrix, final_bits, version)

    # Choose best mask
    best_mask = 0
    best_score = float('inf')
    for mask in range(8):
        masked = _apply_mask(matrix, mask, version, data_area)
        _write_format(masked, mask, version)
        score = _score_matrix(masked)
        if score < best_score:
            best_score = score
            best_mask = mask

    # Apply best mask
    final_matrix = _apply_mask(matrix, best_mask, version, data_area)
    _write_format(final_matrix, best_mask, version)

    # Replace any remaining None with 0
    for r in range(size):
        for c in range(size):
            if final_matrix[r][c] is None or final_matrix[r][c] == 'F':
                final_matrix[r][c] = 0

    # Generate SVG
    total_size = (size + 2 * quiet_zone) * module_size
    rects = []
    for r in range(size):
        for c in range(size):
            if final_matrix[r][c] == 1:
                x = (c + quiet_zone) * module_size
                y = (r + quiet_zone) * module_size
                rects.append(f'<rect x="{x}" y="{y}" width="{module_size}" height="{module_size}"/>')

    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="0 0 {total_size} {total_size}" '
        f'width="{total_size}" height="{total_size}" '
        f'shape-rendering="crispEdges">'
        f'<rect width="{total_size}" height="{total_size}" fill="white"/>'
        f'<g fill="black">{"".join(rects)}</g>'
        f'</svg>'
    )
    return svg


def generate_qr_data_url(text: str) -> str:
    """Return a data URL for the QR code SVG (for embedding in HTML)."""
    import base64
    svg = generate_qr_svg(text)
    b64 = base64.b64encode(svg.encode()).decode()
    return f"data:image/svg+xml;base64,{b64}"
