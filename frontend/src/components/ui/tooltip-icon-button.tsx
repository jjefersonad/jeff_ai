import React from "react";
import { Button } from "./button";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "./tooltip";

interface TooltipIconButtonProps {
  icon: React.ReactNode;
  onClick: () => void;
  tooltip: string;
  /** Defaults to `tooltip` so the button always has an accessible name. */
  ariaLabel?: string;
  disabled?: boolean;
}

export function TooltipIconButton({
  icon,
  onClick,
  tooltip,
  ariaLabel,
  disabled,
}: TooltipIconButtonProps) {
  return (
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger asChild>
          <Button
            variant="ghost"
            size="icon"
            onClick={onClick}
            disabled={disabled}
            aria-label={ariaLabel ?? tooltip}
          >
            {icon}
          </Button>
        </TooltipTrigger>
        <TooltipContent>
          <p>{tooltip}</p>
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}
