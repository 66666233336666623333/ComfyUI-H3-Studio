import test from "node:test";
import assert from "node:assert/strict";
import { counts, emptySelection, planFiles, readSelection, toggleAll } from "../js/selector_state.mjs";

test("mixed batch uses stable free slots and does not mutate saved state", () => {
    const state = emptySelection();
    state.image[0] = { path: "old.png", enabled: false };
    const copy = structuredClone(state);
    const plan = planFiles(state, [{ name: "A.PNG" }, { name: "B.wav" }, { name: "C.mkv" }, { name: "D.png" }]);
    assert.deepEqual(plan.map(({ kind, index }) => [kind, index]), [["image", 1], ["audio", 0], ["video", 0], ["image", 2]]);
    assert.deepEqual(state, copy);
});
test("invalid or overflowing batch leaves old manifest intact", () => {
    const state = emptySelection(), copy = structuredClone(state);
    assert.throws(() => planFiles(state, Array.from({ length: 10 }, () => ({ name: "a.png" }))), /9/);
    assert.throws(() => planFiles(state, [{ name: "a.png" }, { name: "bad.txt" }]), /不支持/);
    assert.deepEqual(state, copy);
});
test("one-slot replace accepts exactly one matching file", () => {
    const target = { kind: "video", index: 2 };
    assert.equal(planFiles(emptySelection(), [{ name: "a.mp4" }], target)[0].index, 2);
    assert.throws(() => planFiles(emptySelection(), [{ name: "a.wav" }], target));
    assert.throws(() => planFiles(emptySelection(), [], target));
});
test("toggles preserve filenames and sparse port positions across serialization", () => {
    const state = emptySelection();
    state.image[8] = { path: "h3_references/last.png", enabled: true };
    const off = toggleAll(state, false);
    assert.equal(counts(off).total, 0);
    assert.equal(off.image[8].path, state.image[8].path);
    assert.equal(state.image[8].enabled, true);
    assert.deepEqual(readSelection(JSON.stringify(off)), off);
    assert.equal(counts(toggleAll(off, true)).total, 1);
});
test("all 15 catalog entries may be retained but count only active files", () => {
    const state = emptySelection();
    for (const entries of Object.values(state)) entries.fill({ path: "file", enabled: true });
    assert.equal(counts(state).total, 15);
    state.video = state.video.map(entry => ({ ...entry, enabled: false }));
    assert.equal(counts(state).total, 12);
});
test("invalid saved manifests are rejected", () => {
    for (const value of ["null", "[]", '{"image":[{}]}', JSON.stringify({ audio: Array(4).fill(null) })]) {
        assert.throws(() => readSelection(value));
    }
});
