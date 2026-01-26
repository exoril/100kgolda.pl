/// <reference path="../pb_data/types.d.ts" />
migrate((app) => {
  const collection = app.findCollectionByNameOrId("pbc_1125843985")

  // update field
  collection.fields.addAt(9, new Field({
    "hidden": false,
    "id": "number300981383",
    "max": null,
    "min": null,
    "name": "views",
    "onlyInt": false,
    "presentable": false,
    "required": false,
    "system": false,
    "type": "number"
  }))

  return app.save(collection)
}, (app) => {
  const collection = app.findCollectionByNameOrId("pbc_1125843985")

  // update field
  collection.fields.addAt(9, new Field({
    "hidden": true,
    "id": "number300981383",
    "max": null,
    "min": null,
    "name": "views",
    "onlyInt": false,
    "presentable": false,
    "required": false,
    "system": false,
    "type": "number"
  }))

  return app.save(collection)
})
