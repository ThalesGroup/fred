import { Autocomplete, Chip, TextField } from "@mui/material";
import { useCallback, useState } from "react";

type TagsInputProps = {
  label?: string;
  helperText?: string;
  value: string[];
  onChange: (next: string[]) => void;
  placeholderWhenEmpty?: string;
  size?: "small" | "medium";
};

export function TagsInput({
  label = "Tags",
  helperText,
  value,
  onChange,
  placeholderWhenEmpty = "no tags",
  size = "small",
}: TagsInputProps) {
  const [inputValue, setInputValue] = useState("");

  const normalize = useCallback((raw: string) => raw.trim(), []);
  const addMany = useCallback(
    (tokens: string[]) => {
      const clean = tokens
        .map(normalize)
        .filter(Boolean)
        .filter((t) => !value.includes(t));
      if (clean.length) onChange([...value, ...clean]);
    },
    [normalize, onChange, value],
  );

  const commitInput = useCallback(() => {
    if (!inputValue.trim()) return;
    addMany(inputValue.split(/[,;\s]+/).filter(Boolean));
    setInputValue("");
  }, [addMany, inputValue]);

  return (
    <Autocomplete
      multiple
      freeSolo
      size={size}
      options={[] as string[]}
      filterOptions={(x) => x}
      value={value}
      onChange={(_, next) => onChange(next.map(normalize))}
      inputValue={inputValue}
      onInputChange={(_, v) => setInputValue(v)}
      renderTags={(tags, getTagProps) =>
        tags.map((option, index) => <Chip label={option} {...getTagProps({ index })} />)
      }
      renderInput={(params) => (
        <TextField
          {...params}
          label={label}
          size={size}
          helperText={helperText}
          placeholder={value.length === 0 ? placeholderWhenEmpty : undefined}
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === " " || e.key === ",") {
              e.preventDefault();
              commitInput();
            }
          }}
          onBlur={commitInput}
          onPaste={(e) => {
            const text = e.clipboardData.getData("text");
            if (text && /[,;\s]/.test(text)) {
              e.preventDefault();
              addMany(text.split(/[,;\s]+/));
              setInputValue("");
            }
          }}
        />
      )}
    />
  );
}
