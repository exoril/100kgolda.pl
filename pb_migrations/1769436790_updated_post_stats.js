/// <reference path="../pb_data/types.d.ts" />
migrate((app) => {
  const collection = app.findCollectionByNameOrId("pbc_1055710165")

  // remove field
  collection.fields.removeById("relation1267270444")

  // add field
  collection.fields.addAt(1, new Field({
    "cascadeDelete": false,
    "collectionId": "pbc_1125843985",
    "hidden": false,
    "id": "relation1519021197",
    "maxSelect": 1,
    "minSelect": 0,
    "name": "post",
    "presentable": false,
    "required": false,
    "system": false,
    "type": "relation"
  }))

  return app.save(collection)
}, (app) => {
  const collection = app.findCollectionByNameOrId("pbc_1055710165")

  // add field
  collection.fields.addAt(1, new Field({
    "cascadeDelete": false,
    "collectionId": "pbc_1055710165",
    "hidden": false,
    "id": "relation1267270444",
    "maxSelect": 1,
    "minSelect": 0,
    "name": "post_id",
    "presentable": false,
    "required": false,
    "system": false,
    "type": "relation"
  }))

  // remove field
  collection.fields.removeById("relation1519021197")

  return app.save(collection)
})
