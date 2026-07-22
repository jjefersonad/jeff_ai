"use client";

import React, { useState, useCallback } from "react";
import useSWR from "swr";
import { ImageGrid } from "@/app/components/ImageGallery";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { ImageIcon, ChevronLeft, ChevronRight } from "lucide-react";

interface ImagesResponse {
  images: Array<{
    filename: string;
    url: string;
    timestamp: string;
  }>;
  total: number;
  limit: number;
  offset: number;
}

const fetcher = (url: string) => fetch(url).then((res) => res.json());

const PAGE_SIZE = 20;

export default function ImagesPage() {
  const [page, setPage] = useState(0);
  const offset = page * PAGE_SIZE;

  const { data, error, isLoading } = useSWR<ImagesResponse>(
    `/api/images?limit=${PAGE_SIZE}&offset=${offset}`,
    fetcher
  );

  const totalPages = data ? Math.ceil(data.total / PAGE_SIZE) : 0;
  const hasNext = data ? offset + PAGE_SIZE < data.total : false;
  const hasPrev = page > 0;

  const goNext = useCallback(() => setPage((p) => p + 1), []);
  const goPrev = useCallback(() => setPage((p) => Math.max(0, p - 1)), []);

  return (
    <div className="min-h-screen bg-background">
      {/* Header */}
      <header className="sticky top-0 z-40 border-b border-border bg-background/80 backdrop-blur-sm">
        <div className="mx-auto flex max-w-[1280px] items-center gap-3 px-6 py-4">
          <ImageIcon size={24} className="text-primary" />
          <h1 className="text-xl font-semibold">Imagens Geradas</h1>
          {data && data.total > 0 && (
            <span className="ml-auto text-sm text-muted-foreground">
              {data.total} imagens
            </span>
          )}
        </div>
      </header>

      {/* Main content */}
      <main className="mx-auto max-w-[1280px] px-6 py-6">
        {error && (
          <div className="flex flex-col items-center justify-center py-16 text-destructive">
            <p className="text-lg font-medium">Erro ao carregar imagens</p>
            <p className="text-sm mt-1">{error.message}</p>
          </div>
        )}

        <ImageGrid
          images={data?.images || []}
          isLoading={isLoading && !data}
        />

        {/* Pagination */}
        {totalPages > 1 && (
          <div className="mt-8 flex items-center justify-center gap-4">
            <Button
              variant="outline"
              size="sm"
              onClick={goPrev}
              disabled={!hasPrev}
            >
              <ChevronLeft size={16} />
              Anterior
            </Button>

            <span className="text-sm text-muted-foreground">
              Página {page + 1} de {totalPages}
            </span>

            <Button
              variant="outline"
              size="sm"
              onClick={goNext}
              disabled={!hasNext}
            >
              Próxima
              <ChevronRight size={16} />
            </Button>
          </div>
        )}
      </main>
    </div>
  );
}
