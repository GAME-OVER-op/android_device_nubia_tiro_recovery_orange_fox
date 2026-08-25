#include <linux/input.h>
#include <stddef.h>

static bool test_bit(unsigned int bit, const unsigned long* bits) {
    const unsigned int bpl = sizeof(unsigned long) * 8U;
    return (bits[bit / bpl] >> (bit % bpl)) & 1UL;
}

int main() {
    const unsigned int bpl = sizeof(unsigned long) * 8U;
    unsigned long ff_bits[(FF_MAX + bpl) / bpl] = {};
    ff_bits[FF_CONSTANT / bpl] |= 1UL << (FF_CONSTANT % bpl);

    struct ff_effect effect = {};
    effect.type = FF_CONSTANT;
    effect.id = -1;
    effect.replay.length = 40;
    effect.u.constant.level = 0x5fff;

    return (test_bit(FF_CONSTANT, ff_bits) &&
            effect.type == FF_CONSTANT &&
            effect.replay.length == 40 &&
            effect.u.constant.level == 0x5fff) ? 0 : 1;
}
