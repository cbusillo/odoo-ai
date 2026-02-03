const path = require('path');

module.exports = {
    resolve: {
        alias: {
            '@opw_custom': path.resolve(__dirname, 'static/src'),
        },
        extensions: ['.js'],
    },
};
