/// <reference path="../pb_data/types.d.ts" />
migrate((app) => {
  const collection = app.findCollectionByNameOrId("pbc_1125843985")

  // add field
  collection.fields.addAt(10, new Field({
    "hidden": false,
    "id": "number851275141",
    "max": null,
    "min": null,
    "name": "like_count",
    "onlyInt": false,
    "presentable": false,
    "required": false,
    "system": false,
    "type": "number"
  }))

  // add field
  collection.fields.addAt(11, new Field({
    "hidden": false,
    "id": "number2786668789",
    "max": null,
    "min": null,
    "name": "love_count",
    "onlyInt": false,
    "presentable": false,
    "required": false,
    "system": false,
    "type": "number"
  }))

  // add field
  collection.fields.addAt(12, new Field({
    "hidden": false,
    "id": "number1762459322",
    "max": null,
    "min": null,
    "name": "laugh_count",
    "onlyInt": false,
    "presentable": false,
    "required": false,
    "system": false,
    "type": "number"
  }))

  return app.save(collection)
}, (app) => {
  const collection = app.findCollectionByNameOrId("pbc_1125843985")

  // remove field
  collection.fields.removeById("number851275141")

  // remove field
  collection.fields.removeById("number2786668789")

  // remove field
  collection.fields.removeById("number1762459322")

  return app.save(collection)
})
