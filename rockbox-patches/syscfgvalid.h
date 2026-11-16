/* syscfgvalid: pure validation for syscfgtool's write stage (no I/O, host-testable). */
#ifndef SYSCFGVALID_H
#define SYSCFGVALID_H

#include <stdint.h>
#include <stddef.h>

#define SCV_SYSCFG_SIZE  0xCC
#define SCV_SECTOR_SIZE  0x1000
#define SCV_HEADER_SIZE  0x18
#define SCV_ENTRY_SIZE   20
#define SCV_NUM_ENTRIES  9

enum scv_result {
    SCV_WRITE = 0,   /* request is valid and NOR differs: write it */
    SCV_NOOP  = 1,   /* request is valid and NOR already holds the target */
    SCV_REFUSE = 2,  /* refuse; reason in why */
};

uint32_t scv_crc32(const uint8_t *buf, size_t len);

/* Parse "<8 hex> <8 hex>" (optional trailing whitespace). Returns 0 on success. */
int scv_parse_req(const char *text, size_t len, uint32_t *crc_cur, uint32_t *crc_new);

/* sector: current NOR 0..SCV_SECTOR_SIZE. target: SCV_SYSCFG_SIZE bytes from syscfg.flash.
 * why: buffer of why_len bytes for a short reason. */
enum scv_result scv_validate(const uint8_t *sector, const uint8_t *target, size_t target_len,
                             uint32_t crc_cur, uint32_t crc_new, char *why, size_t why_len);

#endif
