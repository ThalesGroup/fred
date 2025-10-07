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

import { Box, Button, FormControlLabel, Switch, TextField } from "@mui/material";
import { useState } from "react";
import MarkdownRenderer from "./MarkdownRenderer";
import torture from "./torture.md?raw"; // <-- Vite raw import

export default function RendererPlayground() {
  const [highlight, setHighlight] = useState("renderer");
  const [emoji, setEmoji] = useState(true);
  const [content, setContent] = useState<string>(torture);

  return (
    <Box p={2} display="grid" gap={2}>
      <Box display="flex" gap={2} alignItems="center">
        <TextField
          size="small"
          label="Highlight term"
          value={highlight}
          onChange={(e) => setHighlight(e.target.value)}
        />
        <FormControlLabel
          control={<Switch checked={emoji} onChange={(e) => setEmoji(e.target.checked)} />}
          label="Emoji substitution"
        />
        <Button variant="outlined" onClick={() => setContent(torture)}>
          Reset sample
        </Button>
      </Box>
      <Box border="1px solid" borderColor="divider" borderRadius={2} p={2}>
        <MarkdownRenderer content={content} size="medium" remarkPlugins={[]} enableEmojiSubstitution={emoji} />
      </Box>
    </Box>
  );
}
