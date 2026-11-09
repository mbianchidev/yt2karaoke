class KaraokePitchProcessor extends AudioWorkletProcessor {
  static get parameterDescriptors() {
    return [
      { name: "semitones", defaultValue: 0, minValue: -12, maxValue: 12, automationRate: "k-rate" },
      { name: "mix", defaultValue: 1, minValue: 0, maxValue: 1, automationRate: "k-rate" },
    ];
  }

  constructor() {
    super();
    this.range = Math.ceil(sampleRate * 0.06);
    this.size = this.range + 256;
    this.buffers = [];
    this.position = 0;
    this.phase = 0;
    this.active = true;
    this.port.onmessage = (event) => { if (event.data === "stop") this.active = false; };
  }

  read(buffer, delay) {
    const position = (this.position - delay + this.size) % this.size;
    const index = Math.floor(position);
    const fraction = position - index;
    return buffer[index] * (1 - fraction) + buffer[(index + 1) % this.size] * fraction;
  }

  process(inputs, outputs, parameters) {
    if (!this.active) return false;
    const input = inputs[0] || [];
    const output = outputs[0];
    const semitones = parameters.semitones[0];
    const mix = parameters.mix[0];
    const step = (1 - 2 ** (semitones / 12)) / this.range;
    while (this.buffers.length < output.length) this.buffers.push(new Float32Array(this.size));

    for (let i = 0; i < output[0].length; i++) {
      const secondPhase = (this.phase + 0.5) % 1;
      // Two overlapping delay heads crossfade at their wrap points, preserving the live clock.
      const weight = 0.5 - 0.5 * Math.cos(2 * Math.PI * this.phase);
      for (let channel = 0; channel < output.length; channel++) {
        const dry = (input[channel] || input[0])?.[i] || 0;
        const buffer = this.buffers[channel];
        buffer[this.position] = dry;
        const wet = semitones === 0 ? dry
          : this.read(buffer, 128 + this.phase * this.range) * weight
            + this.read(buffer, 128 + secondPhase * this.range) * (1 - weight);
        output[channel][i] = dry * (1 - mix) + wet * mix;
      }
      this.position = (this.position + 1) % this.size;
      this.phase = (this.phase + step + 1) % 1;
    }
    return true;
  }
}

registerProcessor("karaoke-pitch", KaraokePitchProcessor);
