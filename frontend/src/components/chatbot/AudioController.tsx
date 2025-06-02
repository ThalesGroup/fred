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

import { useEffect, useRef, useState } from "react";
import { Grid2, IconButton, Slider, Typography } from "@mui/material";
import PlayArrowIcon from "@mui/icons-material/PlayArrow";
import PauseIcon from "@mui/icons-material/Pause";
import StopIcon from "@mui/icons-material/Stop";

export default function AudioController({ audioUrl, color }: { audioUrl: string; color: string }) {
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const [isPlaying, setIsPlaying] = useState(false);
  const [progress, setProgress] = useState(0);
  const [currentTime, setCurrentTime] = useState("0:00");
  const [duration, setDuration] = useState("0:00");
  const animationRef = useRef<number | null>(null); // For smooth slider updates

  useEffect(() => {
    if (audioUrl) {
      stopAudio(); // Reset audio when a new URL is passed
    }

    return () => {
      // Cleanup when component unmounts
      if (audioRef.current) {
        audioRef.current.pause();
      }
      if (animationRef.current) {
        cancelAnimationFrame(animationRef.current);
      }
    };
  }, [audioUrl]);

  const playAudio = () => {
    if (audioRef.current) {
      audioRef.current.play();
      setIsPlaying(true);
      animationRef.current = requestAnimationFrame(updateProgress);
    }
  };

  const pauseAudio = () => {
    if (audioRef.current) {
      audioRef.current.pause();
      setIsPlaying(false);
      if (animationRef.current) {
        cancelAnimationFrame(animationRef.current);
      }
    }
  };

  const stopAudio = () => {
    if (audioRef.current) {
      audioRef.current.pause();
      audioRef.current.currentTime = 0;
      setIsPlaying(false);
      setProgress(0);
      setCurrentTime("0:00");
      if (animationRef.current) {
        cancelAnimationFrame(animationRef.current);
      }
    }
  };

  const updateProgress = () => {
    if (audioRef.current) {
      const progressPercentage = (audioRef.current.currentTime / audioRef.current.duration) * 100;
      setProgress(progressPercentage);
      setCurrentTime(formatTime(audioRef.current.currentTime));
      animationRef.current = requestAnimationFrame(updateProgress);
    }
  };

  const handleLoadedMetadata = () => {
    if (audioRef.current) {
      setDuration(formatTime(audioRef.current.duration));
    }
  };

  const handleSliderChange = (event: Event, newValue: number | number[]) => {
    if (event && audioRef.current) {
      const newTime = ((newValue as number) / 100) * audioRef.current.duration;
      audioRef.current.currentTime = newTime;
      setProgress(newValue as number); // Set the new progress manually
      setCurrentTime(formatTime(newTime));
    }
  };

  // Format seconds into M:SS format
  const formatTime = (time: number): string => {
    const minutes = Math.floor(time / 60);
    const seconds = Math.floor(time % 60)
      .toString()
      .padStart(2, "0");
    return `${minutes}:${seconds}`;
  };

  return (
    <Grid2 container>
      <Grid2 size={12} display="flex" alignItems="center" alignContent="center" justifyContent="center">
        <IconButton onClick={isPlaying ? pauseAudio : playAudio}>
          {isPlaying ? <PauseIcon /> : <PlayArrowIcon />}
        </IconButton>
        <IconButton onClick={stopAudio}>
          <StopIcon />
        </IconButton>
        <Typography display={{ xs: "none", sm: "block" }} variant="body2">
          {currentTime} / {duration}
        </Typography>
      </Grid2>
      {/* Progress slider */}
      <Grid2 size={12}>
        <Slider value={progress} onChange={handleSliderChange} sx={{ width: "100%", p: 0, color: color }} />
        <audio
          ref={audioRef}
          src={audioUrl}
          onLoadedMetadata={handleLoadedMetadata}
          onEnded={() => setIsPlaying(false)}
          style={{ display: "none" }} // Hide native audio controls
        />
      </Grid2>
    </Grid2>
  );
}
