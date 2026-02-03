/// <reference path="../pb_data/types.d.ts" />
migrate((app) => {
  const collection = app.findCollectionByNameOrId("pbc_1055710165")

  // remove field
  collection.fields.removeById("number3562379348")

  // remove field
  collection.fields.removeById("number800360698")

  // remove field
  collection.fields.removeById("number478347909")

  return app.save(collection)
}, (app) => {
  const collection = app.findCollectionByNameOrId("pbc_1055710165")

  // add field
  collection.fields.addAt(4, new Field({
    "hidden": false,
    "id": "number3562379348",
    "max": null,
    "min": null,
    "name": "reactions_like",
    "onlyInt": false,
    "presentable": false,
    "required": false,
    "system": false,
    "type": "number"
  }))

  // add field
  collection.fields.addAt(5, new Field({
    "hidden": false,
    "id": "number800360698",
    "max": null,
    "min": null,
    "name": "reactions_love",
    "onlyInt": false,
    "presentable": false,
    "required": false,
    "system": false,
    "type": "number"
  }))

  // add field
  collection.fields.addAt(6, new Field({
    "hidden": false,
    "id": "number478347909",
    "max": null,
    "min": null,
    "name": "reactions_laugh",
    "onlyInt": false,
    "presentable": false,
    "required": false,
    "system": false,
    "type": "number"
  }))

  return app.save(collection)
})
