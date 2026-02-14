/// <reference path="../pb_data/types.d.ts" />
migrate((app) => {
  const collection = app.findCollectionByNameOrId("pbc_1125843985")

  // add field
  collection.fields.addAt(11, new Field({
    "hidden": true,
    "id": "number300981383",
    "max": null,
    "min": null,
    "name": "views",
    "onlyInt": true,
    "presentable": false,
    "required": false,
    "system": false,
    "type": "number"
  }))

  // add field
  collection.fields.addAt(12, new Field({
    "hidden": true,
    "id": "number1604228650",
    "max": null,
    "min": null,
    "name": "comments",
    "onlyInt": true,
    "presentable": false,
    "required": false,
    "system": false,
    "type": "number"
  }))

  return app.save(collection)
}, (app) => {
  const collection = app.findCollectionByNameOrId("pbc_1125843985")

  // remove field
  collection.fields.removeById("number300981383")

  // remove field
  collection.fields.removeById("number1604228650")

  return app.save(collection)
})
