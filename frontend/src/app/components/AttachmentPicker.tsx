"use client";

import React, { useCallback, useRef, useState } from "react";
import { FileIcon, X } from "lucide-react";
import { Button } from "@/components/ui/button";

const ALLOWED_EXTENSIONS = [
  ".png",
  ".jpg",
  ".jpeg",
  ".gif",
  ".webp",
  ".pdf",
  ".docx",
  ".xlsx",
  ".csv",
  ".txt",
];

const UNSUPPORTED_TYPE_ERROR =
  "Unsupported file type. Supported: images, PDF, DOCX, XLSX, CSV, TXT.";

interface AttachmentPickerProps {
  attachments: File[];
  onAttachmentsChange: (files: File[]) => void;
  disabled?: boolean;
}

function extensionOf(filename: string): string {
  const dot = filename.lastIndexOf(".");
  return dot === -1 ? "" : filename.slice(dot).toLowerCase();
}

export function AttachmentPicker({
  attachments,
  onAttachmentsChange,
  disabled,
}: AttachmentPickerProps) {
  const inputRef = useRef<HTMLInputElement | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0];
      e.target.value = ""; // permite reenviar o mesmo arquivo
      if (!file) return;

      if (!ALLOWED_EXTENSIONS.includes(extensionOf(file.name))) {
        setError(UNSUPPORTED_TYPE_ERROR);
        return;
      }

      setError(null);
      onAttachmentsChange([...attachments, file]);
    },
    [attachments, onAttachmentsChange]
  );

  const removeAttachment = useCallback(
    (index: number) => {
      onAttachmentsChange(attachments.filter((_, i) => i !== index));
    },
    [attachments, onAttachmentsChange]
  );

  return (
    <div className="flex flex-col gap-1">
      <input
        ref={inputRef}
        type="file"
        accept={ALLOWED_EXTENSIONS.join(",")}
        onChange={handleChange}
        className="hidden"
        aria-label="Attach a file"
      />
      <Button
        type="button"
        variant="ghost"
        onClick={() => inputRef.current?.click()}
        disabled={disabled}
        title="Attach a file"
        aria-label="Open attachment picker"
      >
        <FileIcon size={16} />
      </Button>
      {error && <p className="text-xs text-destructive">{error}</p>}
      {attachments.length > 0 && (
        <ul className="flex flex-wrap gap-1">
          {attachments.map((file, index) => (
            <li
              key={`${file.name}-${index}`}
              className="flex items-center gap-1 rounded-md border border-border bg-muted/40 px-1.5 py-0.5 text-xs"
            >
              <span className="max-w-[180px] truncate text-secondary">
                {file.name}
              </span>
              <button
                type="button"
                onClick={() => removeAttachment(index)}
                className="text-tertiary hover:text-primary"
                aria-label={`Remove ${file.name}`}
              >
                <X size={12} />
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
