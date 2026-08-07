import { mutate as globalMutate } from "swr";
import type { MutatorCallback, MutatorOptions } from "swr";

/** Key tipada da listagem de imagens (isola cache por users.id). */
export type ImagesSwrKey = {
  kind: "images";
  userId: string;
  limit: number;
  offset: number;
};

export function imagesSwrKeyFor(
  userId: string | null | undefined,
  limit: number,
  offset: number
): ImagesSwrKey {
  return {
    kind: "images",
    userId: userId ?? "anon",
    limit,
    offset,
  };
}

export function isImagesSwrKey(key: unknown): key is ImagesSwrKey {
  return (
    typeof key === "object" &&
    key !== null &&
    (key as { kind?: unknown }).kind === "images"
  );
}

type GlobalMutate = (
  filter: (key: unknown) => boolean,
  data?: unknown | Promise<unknown> | MutatorCallback,
  opts?: boolean | MutatorOptions
) => Promise<unknown>;

/** Invalida listagens de imagens no cache SWR (login/logout). */
export async function clearImagesSwrCache(
  mutate: GlobalMutate = globalMutate as GlobalMutate
): Promise<void> {
  await mutate(isImagesSwrKey, undefined, { revalidate: false });
}
