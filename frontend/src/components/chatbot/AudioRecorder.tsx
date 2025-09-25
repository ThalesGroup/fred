// Copyright Thales 2025
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

import { useEffect, useRef } from "react";

export default function AudioRecorder({
  height = "40px",
  width = "100%",
  waveWidth = 2, // Default bar width
  color = "#000000", // Default waveform color
  isRecording = false, // Default state used to start/stop recording
  onRecordingComplete, // Function to call when recording is complete
  downloadOnSavePress = false, // Download the recording when the record is stopped
  downloadFileExtension = "mp3", // Default file extension for the recording
}: {
  height?: string;
  width?: string;
  waveWidth?: number;
  color?: string;
  isRecording: boolean;
  onRecordingComplete: (audioBlob: Blob) => void;
  downloadOnSavePress?: boolean;
  downloadFileExtension?: string;
}) {
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunks = useRef<Blob[]>([]);

  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const animationRef = useRef<number | null>(null);

  const audioContextRef = useRef<AudioContext | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const dataArrayRef = useRef<Uint8Array<ArrayBuffer> | null>(null);
  useEffect(() => {
    if (isRecording) {
      startRecording().then((r) => r);
    } else {
      stopRecording();
    }
  }, [isRecording]);

  const startRecording = async (): Promise<void> => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      audioContextRef.current = new (window.AudioContext || (window as any).webkitAudioContext)();
      analyserRef.current = audioContextRef.current.createAnalyser();
      const source = audioContextRef.current.createMediaStreamSource(stream);
      source.connect(analyserRef.current);

      mediaRecorderRef.current = new MediaRecorder(stream);
      audioChunks.current = [];

      mediaRecorderRef.current.ondataavailable = (event: BlobEvent) => {
        audioChunks.current.push(event.data);
      };

      mediaRecorderRef.current.onstop = handleRecordingStop;
      mediaRecorderRef.current.start();

      // Configure analyser for a compact waveform
      analyserRef.current.fftSize = 512; // Adjusted for finer, compact bars
      const bufferLength = analyserRef.current.frequencyBinCount;
      dataArrayRef.current = new Uint8Array(bufferLength);

      // Start drawing the compact waveform
      drawCompactWaveform();
    } catch (error) {
      console.error("Error accessing microphone:", error);
    }
  };

  const stopRecording = (): void => {
    if (mediaRecorderRef.current) {
      mediaRecorderRef.current.stop();
    }
    if (animationRef.current) {
      cancelAnimationFrame(animationRef.current);
    }
  };

  const handleRecordingStop = (): void => {
    const audioBlob = new Blob(audioChunks.current, {
      type: `audio/${downloadFileExtension}`,
    });

    onRecordingComplete(audioBlob);

    if (downloadOnSavePress) {
      downloadRecording(audioBlob);
    }

    if (audioContextRef.current) {
      audioContextRef.current.close();
    }
  };

  const downloadRecording = (audioBlob: Blob): void => {
    const link = document.createElement("a");
    link.href = URL.createObjectURL(audioBlob);
    link.download = `recording.${downloadFileExtension}`;
    link.click();
  };

  const drawCompactWaveform = () => {
    if (!canvasRef.current || !analyserRef.current || !dataArrayRef.current) return;

    const canvas = canvasRef.current;
    const canvasContext = canvas.getContext("2d");
    if (!canvasContext) return;

    const draw = () => {
      if (!analyserRef.current || !dataArrayRef.current) return;

      analyserRef.current.getByteFrequencyData(dataArrayRef.current);
      canvasContext.clearRect(0, 0, canvas.width, canvas.height);

      const barWidth = waveWidth;
      let x = 0;

      for (let i = 0; i < analyserRef.current.frequencyBinCount; i++) {
        const barHeight = dataArrayRef.current[i] / 2; // Scale bar height for compactness
        const y = canvas.height - barHeight; // Draw from bottom to top

        // Draw each bar with a configurable color and spacing
        canvasContext.fillStyle = color;
        canvasContext.fillRect(x, y, barWidth, barHeight);

        x += barWidth + 1; // Space between bars
      }
      animationRef.current = requestAnimationFrame(draw);
    };

    draw();
  };

  return (
    <canvas
      ref={canvasRef}
      style={{
        display: isRecording ? "block" : "none", // Hide canvas when not recording
        width: width, // Make canvas width 100% of the parent container
        height: height, // Make canvas height 100% of the parent container
        border: "1px solid #ddd",
        borderRadius: "5px",
      }}
    />
  );
}
