#include <linux/input.h>
#include <stddef.h>

static bool test_bit(unsigned int bit, const unsigned long* bits) {
    const unsigned int bpl = sizeof(unsigned long) * 8U;
    return (bits[bit / bpl] >> (bit % bpl)) & 1UL;
}

static int choose_effect(const unsigned long* ff_bits) {
    if (test_bit(FF_RUMBLE, ff_bits)) return FF_RUMBLE;
    if (test_bit(FF_CONSTANT, ff_bits)) return FF_CONSTANT;
    return -1;
}

int main() {
    const unsigned int bpl = sizeof(unsigned long) * 8U;
    unsigned long ff_bits[(FF_MAX + bpl) / bpl] = {};

    // Tiro advertises both. The recovery patch must prefer hardware-verified
    // FF_RUMBLE rather than the unreliable FF_CONSTANT path.
    ff_bits[FF_CONSTANT / bpl] |= 1UL << (FF_CONSTANT % bpl);
    ff_bits[FF_RUMBLE / bpl] |= 1UL << (FF_RUMBLE % bpl);
    if (choose_effect(ff_bits) != FF_RUMBLE) return 1;

    struct ff_effect rumble = {};
    rumble.type = FF_RUMBLE;
    rumble.id = -1;
    rumble.replay.length = 50;
    rumble.u.rumble.strong_magnitude = 0x7000;
    rumble.u.rumble.weak_magnitude = 0x4000;
    if (rumble.type != FF_RUMBLE || rumble.replay.length != 50 ||
        rumble.u.rumble.strong_magnitude != 0x7000 ||
        rumble.u.rumble.weak_magnitude != 0x4000) return 2;

    // Constant remains a compatibility fallback only when RUMBLE is absent.
    ff_bits[FF_RUMBLE / bpl] &= ~(1UL << (FF_RUMBLE % bpl));
    return choose_effect(ff_bits) == FF_CONSTANT ? 0 : 3;
}
