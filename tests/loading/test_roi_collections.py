import pytest

from embed_data_graph import DatasetGraph, MammogramImage, RegionOfInterest, load_embed

PATH = "/data/cohort1/P/study/series/SOP.dcm"


def test_supplied_depth_flag_is_retained_without_inventing_frames():
    graph = load_embed(images=[row(ROI_coords="[(1,2,10,20)]", ROI_depth_derived=True)]).graph
    roi = graph.rois[0]
    assert roi.frame_indices == ()
    assert roi.frame_provenance == "source_derived"
    assert roi.frame_derivation_method == "ROI_depth_derived"
    load_embed(images=[row(ROI_coords="[(1,2,10,20)]", ROI_frames="[3,4]", ROI_depth_derived=1)], into=graph)
    assert graph.rois[0].frame_indices == (3, 4)



def row(**fields):
    return {"anon_dicom_path": PATH, "acc_anon": "A", "Rows": 100, "Columns": 100, **fields}


def test_metadata_projects_singleton_roi_with_zero_ordinal():
    report = load_embed(images=(item for item in [row(ROI_coords="[(1,2,10,20)]")]))
    image = report.graph.source_image("SOP")
    assert image.image_id == "SOP"
    assert len(image.rois) == 1
    roi = image.rois[0]
    assert roi.roi_key == "0" and roi.collection_position == 0
    assert roi.coordinates == (1, 2, 11, 21)
    assert report.graph.roi_at_source(PATH, 0) is roi


def test_relocation_and_source_reload_after_toolkit_rekey():
    graph = load_embed(images=[row(ROI_coords="[(1,2,10,20)]")]).graph
    image = graph.source_image("SOP")
    image.rekey(image_id="processed")
    relocated = PATH.replace("/data", "/new")
    load_embed(images=[row(anon_dicom_path=relocated, Rows=200)], into=graph)
    assert graph.source_image("SOP") is image and len(graph.images) == 1
    assert image.height == 200 and image.image_id == "processed"
    assert graph.roi_at_source(relocated, 0) is image.rois[0]
    assert graph.roi_at_source(PATH, 0) is image.rois[0]
    assert graph.roi("processed", "0") is image.rois[0]


def test_explicit_uid_wins_and_derivative_does_not_overwrite_original():
    maps = {"images": {"source_sop_instance_uid": "uid", "image_id": "toolkit", "derived_from": "parent"}}
    report = load_embed(images=[row(uid="explicit")], columns=maps)
    graph, original = report.graph, report.graph.source_image("explicit")
    assert original is not None and graph.source_image("SOP") is None
    assert any(issue.code == "source_sop_path_mismatch" for issue in report.issues)
    load_embed(images=[row(uid="explicit", toolkit="derivative", parent="explicit", Rows=50)], columns=maps, into=graph)
    assert graph.source_image("explicit") is original
    assert graph.image("derivative") is not original
    assert original.height == 100


@pytest.mark.parametrize("roi_input", [None, "missing"])
def test_missing_or_null_collection_preserves_annotations(roi_input):
    graph = load_embed(images=[row(ROI_coords="[(1,2,10,20)]")]).graph
    roi = graph.rois[0]
    fields = {} if roi_input == "missing" else {"ROI_coords": None}
    load_embed(images=[row(**fields)], into=graph)
    assert graph.rois == (roi,)


def test_empty_collection_clears_but_empty_table_does_not_address_images():
    graph = load_embed(images=[row(ROI_coords="[(1,2,10,20)]")]).graph
    load_embed(rois=[], into=graph)
    assert len(graph.rois) == 1
    load_embed(rois=[row(ROI_coords="[]")], into=graph)
    assert not graph.rois and graph.roi_at_source(PATH, 0) is None


def test_malformed_or_conflicting_collection_preserves_old_but_metadata_updates():
    graph = load_embed(images=[row(ROI_coords="[(1,2,10,20)]")]).graph
    old = graph.rois[0]
    report = load_embed(images=[row(Rows=200, ROI_coords="oops")], into=graph)
    assert report.issues and graph.rois == (old,) and graph.source_image("SOP").height == 200
    report = load_embed(images=[row(ROI_coords="[]"), row(ROI_coords="[(2,3,4,5)]")], into=graph)
    assert any(i.code == "conflicting_roi_collections" for i in report.issues)
    assert graph.rois == (old,)


def test_repeated_equal_collections_deduplicate_rows_not_annotation_slots():
    collection = "[(1,2,3,4),(1,2,3,4)]"
    graph = load_embed(images=[row(ROI_coords=collection), row(ROI_coords=collection)]).graph
    assert len(graph.rois) == 2
    assert [roi.roi_key for roi in graph.rois] == ["0", "1"]


def test_explicit_roi_rows_override_only_addressed_automatic_collections():
    graph = load_embed(images=[row(ROI_coords="[(1,2,3,4)]")], rois=[row(ROI_coords="[]")]).graph
    assert not graph.rois
    load_embed(images=[row(ROI_coords="[(1,2,3,4)]")], rois=[row(ROI_coords=None)], into=graph)
    assert not graph.rois


def test_roi_only_shell_preserves_parent_metadata_and_later_resolves():
    graph = load_embed(rois=[row(ROI_coords="[(1,2,3,4)]")]).graph
    image, roi = graph.images[0], graph.rois[0]
    load_embed(images=[row(Rows=123)], into=graph)
    assert graph.source_image("SOP") is image
    assert image.rois == (roi,) and image.height == 123
    load_embed(rois=[row(ROI_coords="[]")], into=graph)
    assert image.height == 123


def test_collection_replacement_under_merge_removes_manual_and_old_objects():
    graph = load_embed(images=[row(ROI_coords="[(1,2,3,4)]")]).graph
    image = graph.images[0]
    old = image.rois[0]
    manual = image.add_roi(RegionOfInterest((0,0,1,1), image.image_id, "manual"))
    load_embed(images=[row(ROI_coords="[(2,3,4,5)]")], mode="merge", into=graph)
    assert len(image.rois) == 1 and old.graph is None and manual.graph is None
    assert image.rois[0] is not old
    graph.register(manual)
    assert manual in image.rois


def test_invalid_path_can_load_explicit_identity_and_frame_facts_are_not_inferred():
    report = load_embed(images=[row(anon_dicom_path="invalid", uid="U", ImagesInAcquisition=10, FinalImageType="DBT", ROI_coords="[(0,0,1,1)]")], columns={"images":{"source_sop_instance_uid":"uid"}})
    assert report.graph.source_image("U") is not None
    assert report.graph.rois[0].source_frame_indices == ()
    assert any(i.code == "unparseable_image_path" for i in report.issues)


def test_unbound_image_fields_and_merge_null_fields_preserve_current_values():
    graph = DatasetGraph()
    image = graph.register(MammogramImage("SOP", source_sop_instance_uid="SOP", height=123))
    load_embed(images=[row()], columns={"images":{"height":None}}, into=graph)
    assert image.height == 123
    load_embed(images=[row(Rows=None)], mode="merge", into=graph)
    assert image.height == 123
def test_derivative_metadata_roi_does_not_replace_original_collection_or_alias():
    graph = load_embed(images=[row(ROI_coords="[(1,2,3,4)]")]).graph
    source = graph.source_image("SOP")
    original_roi = source.rois[0]
    maps = {"images": {"image_id": "toolkit", "derived_from": "parent"}}
    load_embed(images=[row(toolkit="derived", parent="SOP", ROI_coords="[(5,6,7,8)]")], into=graph, columns=maps)
    derived = graph.image("derived")
    assert derived.rois[0].coordinates == (5, 6, 8, 9)
    assert source.rois == (original_roi,)
    assert graph.source_image("SOP") is source
    assert graph.roi_at_source(PATH, 0) is original_roi
def test_depth_flags_align_with_each_roi_and_malformed_flags_preserve_snapshot():
    graph = load_embed(images=[row(ROI_coords="[(1,2,3,4),(5,6,7,8)]", ROI_frames="[[2],[3]]", ROI_depth_derived="[True,False]")]).graph
    first, second = graph.rois
    assert first.frame_provenance == "source_derived"
    assert second.frame_provenance == "source_supplied"
    assert first.frame_indices == (2,) and second.frame_indices == (3,)
    result = load_embed(images=[row(ROI_coords="[(1,2,3,4),(5,6,7,8)]", ROI_depth_derived="[True]")], into=graph)
    assert graph.rois == (first, second)
    assert any(issue.code == "invalid_roi_collection" for issue in result.issues)
