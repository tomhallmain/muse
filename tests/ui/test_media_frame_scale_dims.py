"""
Unit tests for ui_qt/media_frame.py's scale_dims().

The app builds its MediaFrame with fill_canvas=True, so _show_image_in_view
takes the maximize path for every image it displays.
"""
import pytest

from ui_qt.media_frame import scale_dims


@pytest.mark.ui
class TestScaleDims:
    def test_an_image_that_already_fits_is_untouched(self):
        assert scale_dims((100, 50), (200, 200)) == (100, 50)
        assert scale_dims((100, 200), (100, 200)) == (100, 200)
        assert scale_dims((50, 80), (100, 200)) == (50, 80)

    def test_a_wider_image_is_bounded_by_width(self):
        assert scale_dims((400, 200), (100, 200)) == (100, 50)
        assert scale_dims((400, 100), (200, 200)) == (200, 50)

    def test_a_taller_image_is_bounded_by_height(self):
        assert scale_dims((100, 400), (200, 200)) == (50, 200)
        assert scale_dims((200, 400), (200, 100)) == (50, 100)

    def test_maximize_grows_a_smaller_image_to_the_box(self):
        assert scale_dims((100, 50), (200, 200), maximize=True) == (200, 100)
        assert scale_dims((50, 100), (200, 200), maximize=True) == (100, 200)

    def test_without_maximize_a_smaller_image_stays_small(self):
        assert scale_dims((100, 50), (200, 200), maximize=False) == (100, 50)

    def test_a_square_image_in_a_square_box_is_unchanged(self):
        assert scale_dims((200, 200), (200, 200), maximize=True) == (200, 200)

    @pytest.mark.parametrize(
        "dims", [(100, 50), (50, 100), (16, 9), (9, 16), (1000, 3), (3, 1000)]
    )
    @pytest.mark.parametrize("box", [(200, 200), (320, 180)])
    def test_the_result_always_fits_the_box(self, dims, box):
        """Growing to meet one side without checking the other overflows the
        box: a 100x50 image in a 200x200 viewport yields 400x200, a pixmap
        larger than the view _show_image_in_view puts it in."""
        width, height = scale_dims(dims, box, maximize=True)
        assert width <= box[0] and height <= box[1]

        width, height = scale_dims(dims, box, maximize=False)
        assert width <= box[0] and height <= box[1]

    @pytest.mark.parametrize("dims", [(1000, 3), (3, 1000)])
    def test_an_extreme_ratio_does_not_collapse_a_side_to_zero(self, dims):
        """A zero-width QPixmap is not renderable."""
        width, height = scale_dims(dims, (200, 200))
        assert width >= 1 and height >= 1

    @pytest.mark.parametrize("dims", [(0, 0), (0, 100), (100, 0), (-5, 10)])
    def test_degenerate_dimensions_do_not_divide_by_zero(self, dims):
        assert scale_dims(dims, (200, 200), maximize=True) == (200, 200)
        assert scale_dims(dims, (200, 200)) == (200, 200)

    def test_a_zero_sized_box_yields_a_renderable_size(self):
        """A viewport measured before layout can report no size."""
        assert scale_dims((100, 50), (0, 0), maximize=True) == (1, 1)
