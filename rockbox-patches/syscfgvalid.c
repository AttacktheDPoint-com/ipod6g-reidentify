/* syscfgvalid: pure validation for syscfgtool's write stage. See docs/spec-automation.md. */
#include <string.h>
#include "syscfgvalid.h"

/* Same as zlib/Python crc32 (IEEE 802.3, reflected 0xEDB88320). */
uint32_t scv_crc32(const uint8_t *buf, size_t len)
{
    uint32_t crc = 0xFFFFFFFFu;
    for (size_t i = 0; i < len; i++) {
        crc ^= buf[i];
        for (int k = 0; k < 8; k++)
            crc = (crc >> 1) ^ (0xEDB88320u & (0u - (crc & 1u)));
    }
    return ~crc;
}

static int hexval(char c)
{
    if (c >= '0' && c <= '9') return c - '0';
    if (c >= 'a' && c <= 'f') return c - 'a' + 10;
    if (c >= 'A' && c <= 'F') return c - 'A' + 10;
    return -1;
}

static int parse_hex8(const char *p, uint32_t *out)
{
    uint32_t v = 0;
    for (int i = 0; i < 8; i++) {
        int h = hexval(p[i]);
        if (h < 0)
            return -1;
        v = (v << 4) | (uint32_t)h;
    }
    *out = v;
    return 0;
}

int scv_parse_req(const char *text, size_t len, uint32_t *crc_cur, uint32_t *crc_new)
{
    if (len < 17 || text[8] != ' ')
        return -1;
    if (parse_hex8(text, crc_cur) || parse_hex8(text + 9, crc_new))
        return -1;
    for (size_t i = 17; i < len; i++)
        if (text[i] != '\r' && text[i] != '\n' && text[i] != ' ')
            return -1;
    return 0;
}

static size_t len16(const uint8_t *s)
{
    size_t n = 0;
    while (n < 16 && s[n])
        n++;
    return n;
}

static uint32_t le32(const uint8_t *p)
{
    return p[0] | (p[1] << 8) | (p[2] << 16) | ((uint32_t)p[3] << 24);
}

/* Header + entry-count + per-entry tag sanity for a 204-byte SysCFG. */
static int header_ok(const uint8_t *c)
{
    return memcmp(c, "gfCS", 4) == 0
        && le32(c + 4) == SCV_SYSCFG_SIZE
        && le32(c + 0x14) == SCV_NUM_ENTRIES;
}

/* Tags stored byte-reversed: "SrNm" is stored as "mNrS". */
static const uint8_t *entry_by_tag(const uint8_t *c, const char *tag)
{
    for (int i = 0; i < SCV_NUM_ENTRIES; i++) {
        const uint8_t *e = c + SCV_HEADER_SIZE + i * SCV_ENTRY_SIZE;
        if (e[0] == tag[3] && e[1] == tag[2] && e[2] == tag[1] && e[3] == tag[0])
            return e + 4;
    }
    return NULL;
}

static enum scv_result refuse(char *why, size_t why_len, const char *msg)
{
    if (why && why_len) {
        strncpy(why, msg, why_len - 1);
        why[why_len - 1] = '\0';
    }
    return SCV_REFUSE;
}

enum scv_result scv_validate(const uint8_t *sector, const uint8_t *target, size_t target_len,
                             uint32_t crc_cur, uint32_t crc_new, char *why, size_t why_len)
{
    static const char *const immutable[] = { "HwId", "Codc", "MLBN" };
    static const char *const mutable_[] = { "FwId", "HwVr", "SwVr", "Mod#", "Regn" };

    if (target_len != SCV_SYSCFG_SIZE)
        return refuse(why, why_len, "syscfg.flash wrong size");

    /* current NOR */
    if (!header_ok(sector))
        return refuse(why, why_len, "NOR SysCFG header invalid");
    for (size_t i = SCV_SYSCFG_SIZE; i < SCV_SECTOR_SIZE; i++)
        if (sector[i] != 0xFF)
            return refuse(why, why_len, "NOR sector 0 tail not blank");
    /* every one of the nine tags exactly once */
    {
        static const char *const all[] = { "SrNm", "FwId", "HwId", "HwVr", "Codc",
                                           "SwVr", "MLBN", "Mod#", "Regn" };
        for (size_t k = 0; k < 9; k++) {
            int n = 0;
            for (int i = 0; i < SCV_NUM_ENTRIES; i++) {
                const uint8_t *e = sector + SCV_HEADER_SIZE + i * SCV_ENTRY_SIZE;
                if (e[0] == all[k][3] && e[1] == all[k][2] && e[2] == all[k][1] && e[3] == all[k][0])
                    n++;
            }
            if (n != 1)
                return refuse(why, why_len, "NOR SysCFG tag missing or duplicated");
        }
    }

    /* target */
    if (scv_crc32(target, SCV_SYSCFG_SIZE) != crc_new)
        return refuse(why, why_len, "syscfg.flash CRC mismatch");
    /* replay of an already-applied request: NOR == target is a no-op, not a refusal */
    if (memcmp(sector, target, SCV_SYSCFG_SIZE) == 0) {
        refuse(why, why_len, "already applied");
        return SCV_NOOP;
    }
    if (scv_crc32(sector, SCV_SYSCFG_SIZE) != crc_cur)
        return refuse(why, why_len, "NOR CRC != flash.req (stale request or wrong unit)");
    if (memcmp(sector, target, SCV_HEADER_SIZE) != 0)
        return refuse(why, why_len, "header differs");
    for (int i = 0; i < SCV_NUM_ENTRIES; i++) {
        const uint8_t *a = sector + SCV_HEADER_SIZE + i * SCV_ENTRY_SIZE;
        const uint8_t *b = target + SCV_HEADER_SIZE + i * SCV_ENTRY_SIZE;
        if (memcmp(a, b, 4) != 0)
            return refuse(why, why_len, "tag sequence differs");
    }
    for (size_t i = 0; i < sizeof(immutable) / sizeof(immutable[0]); i++) {
        const uint8_t *a = entry_by_tag(sector, immutable[i]);
        const uint8_t *b = entry_by_tag(target, immutable[i]);
        if (!a || !b || memcmp(a, b, 16) != 0)
            return refuse(why, why_len, "immutable field differs (HwId/Codc/MLBN)");
    }
    /* SrNm: identical except the 3-char suffix of the NUL-terminated serial */
    {
        const uint8_t *a = entry_by_tag(sector, "SrNm");
        const uint8_t *b = entry_by_tag(target, "SrNm");
        if (!a || !b)
            return refuse(why, why_len, "SrNm missing");
        size_t la = len16(a), lb = len16(b);
        if (la != lb || la < 8 || la > 12)
            return refuse(why, why_len, "serial length differs or implausible");
        if (memcmp(a, b, la - 3) != 0)
            return refuse(why, why_len, "serial stem differs (wrong unit)");
        for (size_t i = la; i < 16; i++)
            if (a[i] != 0 || b[i] != 0)
                return refuse(why, why_len, "serial padding not zero");
    }
    /* every remaining entry must be one of the allowed tags (none else may exist) */
    for (int i = 0; i < SCV_NUM_ENTRIES; i++) {
        const uint8_t *e = sector + SCV_HEADER_SIZE + i * SCV_ENTRY_SIZE;
        char tag[5] = { (char)e[3], (char)e[2], (char)e[1], (char)e[0], 0 };
        int known = !strcmp(tag, "SrNm");
        for (size_t k = 0; k < 3; k++) known |= !strcmp(tag, immutable[k]);
        for (size_t k = 0; k < 5; k++) known |= !strcmp(tag, mutable_[k]);
        if (!known)
            return refuse(why, why_len, "unknown tag in SysCFG");
    }

    refuse(why, why_len, "ok");
    return SCV_WRITE;
}
