$(function() {
    var autotick = function() {
        $('time.autotick').each(function() {
            $(this).attr('datetime');

            var timer = Date.now() - new Date($(this).attr('datetime'));
            if ($(this).data('latency')) {
                timer += $(this).data('latency');
            }
            var negative = timer < 0;

            timer = Math.abs(timer);
            var hours = (timer - (timer % 3600000)) / 3600000;
            timer -= hours * 3600000;
            var mins = (timer - (timer % 60000)) / 60000;
            timer -= mins * 60000;
            var secs = (timer - (timer % 1000)) / 1000;
            timer -= secs * 1000;
            var ds = (timer - (timer % 100)) / 100;

            $(this).html(
                (negative ? '-' : '')
                + hours
                + ':' + ('00' + mins).slice(-2)
                + ':' + ('00' + secs).slice(-2)
                + '<small>.' + ('' + ds) + '</small>'
            );
        });

        requestAnimationFrame(autotick);
    };

    autotick();

    window.localiseDates = function() {
        $(this).find('time.datetime').each(function () {
            var date = new Date($(this).attr('datetime'));
            if ($(this).data('latency')) {
                date = new Date(date.getTime() + $(this).data('latency'));
            }
            $(this).html(date.toLocaleString());
            console.log(this);
            console.log(date.toLocaleString());
        });
        $(this).find('time.onlydate').each(function () {
            var date = new Date($(this).attr('datetime'));
            if ($(this).data('latency')) {
                date = new Date(date.getTime() + $(this).data('latency'));
            }
            $(this).html(date.toLocaleDateString());
        });
        $(this).find('time.onlytime').each(function () {
            var date = new Date($(this).attr('datetime'));
            if ($(this).data('latency')) {
                date = new Date(date.getTime() + $(this).data('latency'));
            }
            $(this).html(date.toLocaleTimeString());
        });
    };
    window.localiseDates.call(document.body);
});
