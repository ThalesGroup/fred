// src/components/agentHub/TuningForm.tsx
import { Stack, TextField, FormControlLabel, Checkbox, FormControl, InputLabel, Select, MenuItem, FormHelperText } from "@mui/material";
import { FieldSpec } from "../../slices/agentic/agenticOpenApi";

type Props = {
  fields: FieldSpec[];
  onChange: (index: number, nextDefault: any) => void;  // edits FieldSpec.default
};

export function TuningForm({ fields, onChange }: Props) {
  const render = (f: FieldSpec, i: number) => {
    const helper = f.description || "";
    const value = fields[i]?.default ?? "";

    switch (f.type) {
      case "prompt":
      case "text":
      case "string":
        return (
          <TextField
            key={f.key}
            label={f.title}
            value={value ?? ""}
            onChange={e => onChange(i, e.target.value)}
            helperText={helper}
            fullWidth
            multiline={!!f.ui?.multiline || f.type === "prompt" || f.type === "text"}
            minRows={f.ui?.max_lines || (f.type === "prompt" ? 6 : 1)}
          />
        );
      case "number":
      case "integer":
        return (
          <TextField
            key={f.key}
            type="number"
            label={f.title}
            value={value ?? ""}
            onChange={e => onChange(i, e.target.value === "" ? null : Number(e.target.value))}
            helperText={helper}
            fullWidth
          />
        );
      case "boolean":
        return (
          <FormControl key={f.key}>
            <FormControlLabel
              control={<Checkbox checked={!!value} onChange={e => onChange(i, e.target.checked)} />}
              label={f.title}
            />
            {helper && <FormHelperText>{helper}</FormHelperText>}
          </FormControl>
        );
      case "select":
        return (
          <FormControl key={f.key} fullWidth>
            <InputLabel>{f.title}</InputLabel>
            <Select
              label={f.title}
              value={value ?? ""}
              onChange={e => onChange(i, e.target.value)}
            >
              {(f.enum || []).map(opt => <MenuItem key={opt} value={opt}>{opt}</MenuItem>)}
            </Select>
            {helper && <FormHelperText>{helper}</FormHelperText>}
          </FormControl>
        );
      default:
        return (
          <TextField
            key={f.key}
            label={`${f.title} (not yet editable)`}
            value={JSON.stringify(value ?? f.default ?? "", null, 2)}
            helperText={helper}
            fullWidth
            multiline
            InputProps={{ readOnly: true }}
          />
        );
    }
  };

  return <Stack spacing={1.25}>{fields.map((f, i) => render(f, i))}</Stack>;
}
