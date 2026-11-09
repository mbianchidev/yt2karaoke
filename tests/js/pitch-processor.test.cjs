const assert = require("node:assert/strict");
const { readFileSync } = require("node:fs");
const { resolve } = require("node:path");
const { test } = require("node:test");
const vm = require("node:vm");

const sampleRate = 48000;
let Processor;
vm.runInNewContext(
  readFileSync(resolve(__dirname, "../../src/yt2karaoke/player/static/pitch-processor.js"), "utf8"),
  {
    sampleRate, AudioWorkletProcessor: class { constructor() { this.port = {}; } },
    registerProcessor(name, implementation) {
      assert.equal(name, "karaoke-pitch");
      Processor = implementation;
    },
  },
);

function render(semitones, mix = 1, frequency = 440) {
  const processor = new Processor();
  const length = sampleRate * 2;
  const result = new Float32Array(length);
  for (let offset = 0; offset < length; offset += 128) {
    const input = Float32Array.from(
      { length: 128 }, (_, i) => frequency ? 0.3 * Math.sin(2 * Math.PI * frequency * (offset + i) / sampleRate) : 0,
    );
    const output = new Float32Array(128);
    assert.equal(processor.process([[input]], [[output]], {
      semitones: new Float32Array([semitones]), mix: new Float32Array([mix]),
    }), true);
    result.set(output, offset);
  }
  return result;
}

for (const semitones of [-12, -7, 7, 12]) {
  test(`shifts ${semitones} semitones without changing duration or clipping`, () => {
    const output = render(semitones);
    assert.equal(output.length, sampleRate * 2);
    assert.ok(output.every((value) => Number.isFinite(value) && Math.abs(value) <= 0.301));
    let crossings = 0;
    for (let i = sampleRate + 1; i < output.length; i++) {
      if (output[i - 1] <= 0 && output[i] > 0) crossings++;
    }
    const expected = 440 * 2 ** (semitones / 12);
    assert.ok(Math.abs(crossings - expected) < expected * 0.025, `${crossings} Hz, expected ${expected} Hz`);
  });
}

test("natural voice and a dry mix preserve the input exactly", () => {
  assert.deepEqual(render(0), render(12, 0));
});

test("effect amount blends wet and dry rather than changing the song speed", () => {
  const dry = render(7, 0);
  const wet = render(7, 1);
  const mixed = render(7, 0.25);
  for (let i = 0; i < mixed.length; i++) {
    assert.ok(Math.abs(mixed[i] - (dry[i] * 0.75 + wet[i] * 0.25)) < 0.000001);
  }
});

test("silence stays finite and silent", () => {
  assert.ok(render(-12, 1, 0).every((value) => value === 0));
});

test("stopping the microphone also stops its worklet", () => {
  const processor = new Processor();
  assert.equal(typeof processor.port.onmessage, "function");
  processor.port.onmessage({ data: "stop" });
  assert.equal(processor.process([[]], [[new Float32Array(128)]], {
    semitones: new Float32Array([0]), mix: new Float32Array([1]),
  }), false);
});
