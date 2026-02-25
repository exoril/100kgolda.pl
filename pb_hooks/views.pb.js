/// <reference path="../pb_data/types.d.ts" />

onRecordAfterCreateSuccess(async (e) => {
  // e.record to nowo utworzony rekord w kolekcji "views"
  const postId = e.record.get("post");
  if (!postId) return;

  const app = e.app || $app;

  // Atomowy update w DB (bez read-modify-write, bez wyścigów)
  await app
    .db()
    .newQuery("UPDATE posts SET views = views + 1 WHERE id = {:id}")
    .bind({ id: postId })
    .execute();

  console.log(`[VIEW] posts.views +1 for post=${postId}`);
}, "views");