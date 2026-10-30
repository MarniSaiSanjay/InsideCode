import io
import zipfile


def make_zip(files: dict[str, bytes | str], **zinfo) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in files.items():
            info = zipfile.ZipInfo(name)
            for key, value in zinfo.get(name, {}).items():
                setattr(info, key, value)
            archive.writestr(info, data)
    return buffer.getvalue()
