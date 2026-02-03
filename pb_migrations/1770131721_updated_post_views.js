/// <reference path="../pb_data/types.d.ts" />
migrate((app) => {
  const collection = app.findCollectionByNameOrId("pbc_2019238136")

  // update collection data
  unmarshal({
    "indexes": [
      "CREATE UNIQUE INDEX `idx_PAC4ZHVGKk` ON `post_views` (`key`)"
    ]
  }, collection)

  return app.save(collection)
}, (app) => {
  const collection = app.findCollectionByNameOrId("pbc_2019238136")

  // update collection data
  unmarshal({
    "indexes": []
  }, collection)

  return app.save(collection)
})
