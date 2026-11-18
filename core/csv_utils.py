import csv
from django.http import StreamingHttpResponse


class Echo:
    """An object that implements just the write method of the file-like interface."""
    def write(self, value):
        return value


def csv_row(cells):
    """Escape CSV formula injection: prefix = + - @ with a single quote."""
    return ["'" + c if c and c[0] in ('=', '+', '-', '@') else c for c in cells]


def stream_csv(filename, headers, rows):
    """Stream CSV with UTF-8 BOM for Excel compatibility."""
    def generator():
        yield '\ufeff'  # UTF-8 BOM
        writer = csv.writer(Echo())
        yield writer.writerow(headers)
        for row in rows:
            yield writer.writerow(csv_row(row))
    response = StreamingHttpResponse(generator(), content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response
