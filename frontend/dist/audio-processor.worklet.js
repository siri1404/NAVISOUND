/**
 * AudioProcessor Worklet
 * 
 * Processes microphone audio in chunks and sends Float32 PCM to main thread
 * Chunk size: 4096 samples (~256ms at 16kHz)
 */

class AudioProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this.bufferSize = 4096;
    this.buffer = new Float32Array(this.bufferSize);
    this.bufferIndex = 0;
  }

  process(inputs, outputs, parameters) {
    const input = inputs[0];
    
    // If no input, return true to keep processor alive
    if (!input || !input[0]) {
      return true;
    }

    const inputChannel = input[0]; // mono channel

    // Accumulate samples into buffer
    for (let i = 0; i < inputChannel.length; i++) {
      this.buffer[this.bufferIndex++] = inputChannel[i];

      // When buffer is full, send to main thread
      if (this.bufferIndex >= this.bufferSize) {
        this.port.postMessage({
          type: 'audio-chunk',
          samples: this.buffer.slice(0, this.bufferIndex),
        });

        // Reset buffer
        this.bufferIndex = 0;
      }
    }

    return true; // Keep processor alive
  }
}

registerProcessor('audio-processor', AudioProcessor);
