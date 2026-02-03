/// <reference path="../pb_data/types.d.ts" />
migrate((app) => {
  const collection = app.findCollectionByNameOrId("pbc_1055710165")

  // remove field
  collection.fields.removeById("json947093427")

  return app.save(collection)
}, (app) => {
  const collection = app.findCollectionByNameOrId("pbc_1055710165")

  // add field
  collection.fields.addAt(4, new Field({
    "hidden": false,
    "id": "json947093427",
    "maxSize": 0,
    "name": "reactions",
    "presentable": false,
    "required": false,
    "system": false,
    "type": "json"
  }))

  return app.save(collection)
})
