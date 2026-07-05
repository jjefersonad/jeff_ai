"use client";

import React, { useState, useCallback } from "react";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Dialog,
  DialogContent,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";
import { cn } from "@/lib/utils";

export interface GalleryImage {
  filename: string;
  url: string;
  timestamp: string;
}

interface ImageGridProps {
  images: GalleryImage[];
  isLoading?: boolean;
}

function formatTimestamp(isoString: string): string {
  try {
    const date = new Date(isoString);
    return date.toLocaleString("pt-BR", {
      day: "2-digit",
      month: "2-digit",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return isoString;
  }
}

function ImageModal({
  image,
  open,
  onOpenChange,
}: {
  image: GalleryImage | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  if (!image) return null;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-4xl w-full p-0 border-0 bg-transparent shadow-none">
        <DialogTitle className="sr-only">{image.filename}</DialogTitle>
        <DialogDescription className="sr-only">
          Imagem gerada em {formatTimestamp(image.timestamp)}
        </DialogDescription>
        <div className="relative flex items-center justify-center">
          <img
            src={image.url}
            alt={image.filename}
            className="max-w-full max-h-[85vh] rounded-lg object-contain"
            loading="eager"
          />
        </div>
        <div className="text-center text-white/90 text-sm mt-2">
          {image.filename} — {formatTimestamp(image.timestamp)}
        </div>
      </DialogContent>
    </Dialog>
  );
}

export const ImageGrid = React.memo<ImageGridProps>(
  ({ images, isLoading = false }) => {
    const [selectedImage, setSelectedImage] = useState<GalleryImage | null>(
      null
    );
    const [modalOpen, setModalOpen] = useState(false);
    const [loadedImages, setLoadedImages] = useState<Set<string>>(new Set());

    const openModal = useCallback((image: GalleryImage) => {
      setSelectedImage(image);
      setModalOpen(true);
    }, []);

    const handleImageLoad = useCallback((filename: string) => {
      setLoadedImages((prev) => new Set(prev).add(filename));
    }, []);

    if (isLoading) {
      return (
        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-4">
          {Array.from({ length: 10 }).map((_, i) => (
            <div key={i} className="space-y-2">
              <Skeleton className="aspect-square w-full rounded-lg" />
              <Skeleton className="h-4 w-3/4" />
              <Skeleton className="h-3 w-1/2" />
            </div>
          ))}
        </div>
      );
    }

    if (images.length === 0) {
      return (
        <div className="flex flex-col items-center justify-center py-16 text-muted-foreground">
          <p className="text-lg font-medium">Nenhuma imagem encontrada</p>
          <p className="text-sm mt-1">
            Gere imagens usando o agente para vê-las aqui.
          </p>
        </div>
      );
    }

    return (
      <>
        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-4">
          {images.map((image) => {
            const isLoaded = loadedImages.has(image.filename);
            return (
              <div
                key={image.filename}
                className={cn(
                  "group cursor-pointer rounded-lg border border-border bg-background overflow-hidden transition-all duration-200 hover:border-primary/50 hover:shadow-md",
                  !isLoaded && "opacity-0"
                )}
                onClick={() => openModal(image)}
                style={{ opacity: isLoaded ? 1 : 0 }}
              >
                <div className="relative aspect-square overflow-hidden bg-muted">
                  {!isLoaded && (
                    <Skeleton className="absolute inset-0 aspect-square" />
                  )}
                  <img
                    src={image.url}
                    alt={image.filename}
                    className="h-full w-full object-cover transition-transform duration-300 group-hover:scale-105"
                    loading="lazy"
                    onLoad={() => handleImageLoad(image.filename)}
                  />
                </div>
                <div className="p-2">
                  <p className="text-xs font-mono text-foreground truncate">
                    {image.filename}
                  </p>
                  <p className="text-[10px] text-muted-foreground mt-0.5">
                    {formatTimestamp(image.timestamp)}
                  </p>
                </div>
              </div>
            );
          })}
        </div>

        <ImageModal
          image={selectedImage}
          open={modalOpen}
          onOpenChange={setModalOpen}
        />
      </>
    );
  }
);

ImageGrid.displayName = "ImageGrid";
